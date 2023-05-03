import logging
import os
import typing
import functools
import time

from qtpy import QtCore, QtGui, QtWidgets
from epics import PV
from qt_epics.QtEpicsPVEntry import QtEpicsPVEntry
from qt_epics.QtEpicsPVLabel import QtEpicsPVLabel

import daq_utils
import db_lib
from config_params import (
    VALID_PREFIX_LENGTH,
    VALID_PREFIX_NAME,
    VALID_EXP_TIMES,
    VALID_TOTAL_EXP_TIMES,
    VALID_DET_DIST,
)
from daq_macros import getBlConfig
from threads import RaddoseThread

if typing.TYPE_CHECKING:
    from gui.control_main import ControlMain

logger = logging.getLogger()


class Acquisition(QtWidgets.QGroupBox):
    stillModeStateSignal = QtCore.Signal(int)

    def __init__(self, parent: "ControlMain"):
        QtWidgets.QGroupBox.__init__(self, parent)
        self.parent: "ControlMain" = parent
        self.setTitle("Acquisition")
        self.initPVs()
        self.initUI()

    def initPVs(self):
        self.beamSize_pv = PV(daq_utils.beamlineComm + "size_mode")
        self.beamSize_pv.add_callback(self.beamSizeChangedCB)
        self.stillModeStatePV = PV(daq_utils.pvLookupDict["stillModeStatus"])
        self.stillModeStatePV.add_callback(self.stillModeStateChangedCB)
        self.energy_pv = PV(daq_utils.motor_dict["energy"] + ".RBV")
        self.stillMode_pv = PV(daq_utils.pvLookupDict["stillMode"])
        self.standardMode_pv = PV(daq_utils.pvLookupDict["standardMode"])
        self.sampleFluxPV = PV(daq_utils.pvLookupDict["sampleFlux"])

    def setGuiValues(self, values):
        mapping = {
            "osc_start": self.osc_start_ledit,
            "osc_end": self.osc_range_ledit,
            "osc_range": self.osc_width_ledit,
            "exp_time": self.exp_time_ledit,
            "transmission": self.transmission_ledit,
            "resolution": self.resolution_ledit,
        }
        for item, value in values.items():
            logger.info("resetting %s to %s" % (item, value))
            widget = mapping.get(item, None)
            if widget:
                widget.setText(f"{float(value):.3f}")
            else:
                logger.error("setGuiValues unknown item: %s value: %s" % (item, value))

    def generate_line_edit(self, input: "dict[str, typing.Any]", ledit=None):
        if not ledit:
            ledit = QtWidgets.QLineEdit()

        ledit.setFixedWidth(input.get("width", 60))
        if "validators" in input:
            for validator in input["validators"]:
                ledit.setValidator(validator)

        if "text_changed" in input:
            for cb in input["textchanged"]:
                ledit.textChanged.connect(cb)
        if "return_pressed" in input:
            for cb in input["return_pressed"]:
                ledit.returnPressed.connect(cb)
        return ledit

    def generate_label(self, text="", width=140, alignment=QtCore.Qt.AlignCenter):
        label = QtWidgets.QLabel(text, self)
        if width:
            label.setFixedWidth(width)
        if alignment:
            label.setAlignment(alignment)
        return label

    def resoTextChanged(self, text):
        try:
            dist_s = "%.2f" % (
                daq_utils.distance_from_reso(
                    daq_utils.det_radius,
                    float(text),
                    daq_utils.energy2wave(float(self.energy_ledit.text())),
                    0,
                )
            )
        except ValueError:
            dist_s = self.det_dist_RBV_label.text()
        self.det_dist_motor_entry.setText(dist_s)

    def initUI(self):
        widget_layout = QtWidgets.QVBoxLayout()
        parameter_layout = QtWidgets.QGridLayout()
        parameter_layout = self.setup_first_column_widgets(parameter_layout)
        parameter_layout = self.setup_second_column_widgets(parameter_layout)
        protocol_layout = self.setup_protocol_widgets()

        widget_layout.addLayout(parameter_layout)
        widget_layout.addLayout(protocol_layout)
        self.setLayout(widget_layout)

    def setup_protocol_widgets(self):
        hbox_layout = QtWidgets.QHBoxLayout()
        protoLabel = QtWidgets.QLabel("Protocol:")
        font = QtGui.QFont()
        font.setBold(True)
        protoLabel.setFont(font)
        protoLabel.setAlignment(QtCore.Qt.AlignCenter)
        self.protoRadioGroup = QtWidgets.QButtonGroup()
        self.protoStandardRadio = QtWidgets.QRadioButton("standard")
        self.protoStandardRadio.setChecked(True)
        self.protoStandardRadio.toggled.connect(
            functools.partial(self.protoRadioToggledCB, "standard")
        )
        self.protoStandardRadio.pressed.connect(
            functools.partial(self.protoRadioToggledCB, "standard")
        )
        self.protoRadioGroup.addButton(self.protoStandardRadio)
        self.protoRasterRadio = QtWidgets.QRadioButton("raster")
        self.protoRasterRadio.toggled.connect(
            functools.partial(self.protoRadioToggledCB, "raster")
        )
        self.protoRasterRadio.pressed.connect(
            functools.partial(self.protoRadioToggledCB, "raster")
        )
        self.protoRadioGroup.addButton(self.protoRasterRadio)
        self.protoVectorRadio = QtWidgets.QRadioButton("vector")
        self.protoRasterRadio.toggled.connect(
            functools.partial(self.protoRadioToggledCB, "vector")
        )
        self.protoRasterRadio.pressed.connect(
            functools.partial(self.protoRadioToggledCB, "vector")
        )
        self.protoRadioGroup.addButton(self.protoVectorRadio)
        self.protoOtherRadio = QtWidgets.QRadioButton("other")
        self.protoOtherRadio.setEnabled(False)
        self.protoRadioGroup.addButton(self.protoOtherRadio)
        protoOptionList = [
            "standard",
            "raster",
            "vector",
            "burn",
            "rasterScreen",
            "stepRaster",
            "stepVector",
            "multiCol",
            "characterize",
            "ednaCol",
        ]  # these should probably come from db
        self.protoComboBox = QtWidgets.QComboBox(self)
        self.protoComboBox.addItems(protoOptionList)
        hbox_layout.addWidget(protoLabel)
        hbox_layout.addWidget(self.protoStandardRadio)
        hbox_layout.addWidget(self.protoRasterRadio)
        hbox_layout.addWidget(self.protoVectorRadio)
        hbox_layout.addWidget(self.protoComboBox)
        return hbox_layout

    def setup_first_column_widgets(self, layout: "QtWidgets.QGridLayout"):
        line_edits = {
            "osc_width": {"validators": [QtGui.QDoubleValidator(0.001, 3600, 3)]},
            "osc_start": {"validators": [QtGui.QDoubleValidator()]},
            "osc_range": {
                "validators": [QtGui.QDoubleValidator()],
                "text_changed": [functools.partial(self.totalExpChanged, "oscEnd")],
            },
            "exposure_time": {
                "validators": [
                    QtGui.QDoubleValidator(
                        VALID_EXP_TIMES[daq_utils.beamline]["min"],
                        VALID_EXP_TIMES[daq_utils.beamline]["max"],
                        VALID_EXP_TIMES[daq_utils.beamline]["digits"],
                    )
                ],
                "text_changed": [self.totalExpChanged, self.checkEntryState],
            },
            "total_exposure": {
                "validators": [
                    QtGui.QDoubleValidator(
                        VALID_TOTAL_EXP_TIMES[daq_utils.beamline]["min"],
                        VALID_TOTAL_EXP_TIMES[daq_utils.beamline]["max"],
                        VALID_TOTAL_EXP_TIMES[daq_utils.beamline]["digits"],
                    )
                ],
                "text_changed": self.checkEntryState,
            },
        }
        osc_width_label = self.generate_label("Oscillation Width:")
        self.osc_width_ledit = self.generate_line_edit(line_edits["osc_width"])
        self.osc_width_ledit.textChanged.connect(
            functools.partial(self.totalExpChanged, "oscRange")
        )

        osc_start_label = self.generate_label("Oscillation Start:")
        self.osc_start_ledit = self.generate_line_edit(line_edits["osc_start"])

        self.osc_range_label = self.generate_label("Oscillation Range:")
        self.osc_range_ledit = self.generate_line_edit(line_edits["osc_range"])

        exp_time_label = self.generate_label("Exposure Time:")
        self.exp_time_ledit = self.generate_line_edit(line_edits["exposure_time"])

        total_exp_time_label = self.generate_label("Total Exposure Time(s):")
        self.total_exp_time_ledit = self.generate_line_edit(
            line_edits["total_exposure"]
        )
        self.total_exp_time_ledit.setReadOnly(True)
        self.total_exp_time_ledit.setFrame(False)

        self.stillModeCheckBox = QtWidgets.QCheckBox("Stills")
        self.stillModeCheckBox.setEnabled(False)
        if self.stillModeStatePV.get():
            self.stillModeCheckBox.setChecked(True)
            self.setGuiValues({"osc_range": "0.0"})
            self.osc_width_ledit.setEnabled(False)
        else:
            self.stillModeCheckBox.setChecked(False)
            self.osc_width_ledit.setEnabled(True)

        self.stillModeCheckBox.clicked.connect(self.stillModeUserPushCB)
        centering_label = QtWidgets.QLabel("Sample Centering:")
        centering_label.setFixedWidth(140)
        centering_option_list = ["Interactive", "AutoLoop", "AutoRaster", "Testing"]
        self.centering_combo_box = QtWidgets.QComboBox(self)
        self.centering_combo_box.addItems(centering_option_list)

        # Laying out widget as a list of lists so that we can move it around easily
        widget_layout = [
            [self.stillModeCheckBox],
            [osc_width_label, self.osc_width_ledit],
            [osc_start_label, self.osc_start_ledit],
            [self.osc_range_label, self.osc_range_ledit],
            [exp_time_label, self.exp_time_ledit],
            [total_exp_time_label, self.total_exp_time_ledit],
            [centering_label, self.centering_combo_box],
        ]

        for row, widget_row in enumerate(widget_layout):
            for col, widget in enumerate(widget_row):
                layout.addWidget(widget, row, col)

        return layout

    def setup_second_column_widgets(self, layout: "QtWidgets.QGridLayout"):
        line_edits = {
            "det_dist": {
                "validators": [
                    QtGui.QDoubleValidator(
                        VALID_DET_DIST[daq_utils.beamline]["min"],
                        VALID_DET_DIST[daq_utils.beamline]["max"],
                        VALID_DET_DIST[daq_utils.beamline]["digits"],
                    )
                ],
                "text_changed": [self.detDistTextChanged, self.checkEntryState],
                "return_pressed": [self.moveDetDistCB],
            },
            "edge_resolution": {
                "validators": [QtGui.QDoubleValidator()],
                "text_changed": [self.resoTextChanged],
            },
            "energy": {
                "validators": [QtGui.QDoubleValidator()],
                "return_pressed": [self.moveEnergyCB],
            },
            "transmission": {
                "validators": [QtGui.QDoubleValidator(0.001, 0.999, 3)],
                "return_pressed": [self.setTransCB],
                "text_changed": [],
            },
        }

        det_dist_label = QtWidgets.QLabel("Detector Distance:")
        self.det_dist_RBV_label_epics = QtEpicsPVLabel(
            daq_utils.motor_dict["detectorDist"] + ".RBV", self, 70
        )
        self.det_dist_RBV_label: "QtWidgets.QLabel" = (
            self.det_dist_RBV_label_epics.getEntry()
        )
        self.det_dist_motor_entry_epics = QtEpicsPVEntry(
            daq_utils.motor_dict["detectorDist"] + ".VAL", self, 70, 2
        )
        self.det_dist_motor_entry: "QtWidgets.QLineEdit" = (
            self.det_dist_motor_entry_epics.getEntry()
        )
        self.det_dist_motor_entry = self.generate_line_edit(
            line_edits["det_dist"], self.det_dist_motor_entry
        )

        edge_resolution_label = self.generate_label("Edge Resolution:")
        self.resolution_ledit = self.generate_line_edit(line_edits["edge_resolution"])
        if daq_utils.beamline == "nyx":
            self.resolution_ledit.setEnabled(False)

        energy_label = self.generate_label("Energy (eV):")
        self.energy_motor_entry_epics = QtEpicsPVLabel(
            daq_utils.motor_dict["energy"] + ".RBV", self, 70, 2
        )
        self.energy_readback_label = self.energy_motor_entry_epics.getEntry()
        self.energy_move_ledit_epics = QtEpicsPVEntry(
            daq_utils.motor_dict["energy"] + ".VAL", self, 75, 2
        )
        self.energy_ledit = self.generate_line_edit(
            line_edits["energy"], self.energy_move_ledit_epics.getEntry()
        )

        rb_key = "transmissionRBV"
        set_point_key = "transmissionSet"
        label = "Transmission (0.0-1.0):"
        if daq_utils.beamline in ("fmx", "nyx"):
            if getBlConfig("attenType") == "RI":
                rb_key = "RI_Atten_SP"
                set_point_key = "RI_Atten_SP"
                label = "Transmission (RI) (0.0-1.0):"
            else:
                label = "Transmission (BCU) (0.0-1.0)"
        self.transmissionReadback = QtEpicsPVLabel(
            daq_utils.pvLookupDict[rb_key], self, 60, 3
        )
        self.transmissionSetPoint = QtEpicsPVEntry(
            daq_utils.pvLookupDict[set_point_key], self, 60, 3
        )
        transmission_label = QtWidgets.QLabel(label)
        self.transmission_readback_label = self.transmissionReadback.getEntry()
        self.transmission_ledit = self.transmissionSetPoint.getEntry()
        # self.setGuiValues({"transmission": getBlConfig("stdTrans")})
        if daq_utils.beamline == "fmx":
            line_edits["transmission"]["text_changed"].append(self.calcLifetimeCB)
        self.transmission_ledit = self.generate_line_edit(
            line_edits["transmission"], self.transmission_ledit
        )

        beamsize_label = QtWidgets.QLabel("BeamSize:")
        beamsize_option_list = ["V0H0", "V0H1", "V1H0", "V1H1"]
        self.beamsize_combo_box = QtWidgets.QComboBox(self)
        self.beamsize_combo_box.addItems(beamsize_option_list)
        self.beamsize_combo_box.setCurrentIndex(int(self.beamSize_pv.get()))
        self.beamsize_combo_box.activated.connect(self.beamsizeComboActivatedCB)
        if daq_utils.beamline == "amx" or self.energy_pv.get() < 9000:
            self.beamsize_combo_box.setEnabled(False)

        if daq_utils.beamline == "amx":
            self.sampleLifetimeReadback = QtEpicsPVLabel(
                daq_utils.pvLookupDict["sampleLifetime"], self, 70, 2
            )
            self.sample_lifetime_readback_ledit = self.sampleLifetimeReadback.getEntry()
        else:
            self.sample_lifetime_readback_ledit = QtWidgets.QLabel()
            self.calcLifetimeCB()

        sample_lifetime_label = QtWidgets.QLabel("Estimated Sample Lifetime (s): ")

        widget_layout = [
            [],
            [det_dist_label, self.det_dist_motor_entry, self.det_dist_RBV_label],
            [edge_resolution_label, self.resolution_ledit],
            [energy_label, self.energy_ledit, self.energy_readback_label],
            [
                transmission_label,
                self.transmission_ledit,
                self.transmission_readback_label,
            ],
            [beamsize_label, self.beamsize_combo_box],
            [sample_lifetime_label, self.sample_lifetime_readback_ledit],
        ]

        col_offset = 2
        for row, widget_row in enumerate(widget_layout):
            for col, widget in enumerate(widget_row):
                layout.addWidget(widget, row, col + col_offset)

        return layout

    def checkEntryState(self, *args, **kwargs):
        sender = self.sender()
        validator = sender.validator()
        state = validator.validate(sender.text(), 0)[0]
        if state == QtGui.QValidator.Intermediate:
            color = "#fff79a"  # yellow
        elif state == QtGui.QValidator.Invalid:
            color = "#f6989d"  # red
        else:
            color = "#ffffff"  # white
        sender.setStyleSheet("QLineEdit { background-color: %s }" % color)

    def totalExpChanged(self, text):
        if text == "oscEnd" and daq_utils.beamline == "fmx":
            self.sample_lifetime_readback_ledit.setStyleSheet("color : gray")
        try:
            if float(str(self.osc_width_ledit.text())) == 0:
                if text == "oscRange":
                    if self.parent.controlEnabled():
                        self.stillMode_pv.put(1)
                self.osc_range_ledit.setText("Number of Images: ")
                if (
                    str(self.protoComboBox.currentText()) != "standard"
                    and str(self.protoComboBox.currentText()) != "vector"
                ):
                    self.total_exp_time_ledit.setText("----")
                else:
                    try:
                        totalExptime = float(self.osc_range_ledit.text()) * float(
                            self.exp_time_ledit.text()
                        )
                    except ValueError:
                        totalExptime = 0.0
                    except TypeError:
                        totalExptime = 0.0
                    except ZeroDivisionError:
                        totalExptime = 0.0
                    self.total_exp_time_ledit.setText("%.3f" % totalExptime)
                return
            else:
                if text == "oscRange":
                    if self.parent.controlEnabled():
                        self.standardMode_pv.put(1)
                self.osc_range_ledit.setText("Oscillation Range:")
        except ValueError:
            return

    def detDistTextChanged(self, text):
        try:
            reso_s = "%.2f" % (
                daq_utils.calc_reso(
                    daq_utils.det_radius,
                    float(text),
                    daq_utils.energy2wave(float(self.energy_ledit.text())),
                    0,
                )
            )
        except ValueError:
            reso_s = "50.0"
        except TypeError:
            reso_s = "50.0"
        self.setGuiValues({"resolution": reso_s})

    def moveDetDistCB(self):
        comm_s = f'mvaDescriptor("detectorDist",{self.det_dist_motor_entry.text()})'
        logger.info(comm_s)
        self.parent.send_to_server(comm_s)

    def stillModeStateChangedCB(self, value=None, char_value=None, **kw):
        state = value
        self.stillModeStateSignal.emit(state)

    def moveEnergyCB(self):
        energyRequest = float(str(self.energy_ledit.text()))
        if abs(energyRequest - self.energy_pv.get()) > 10.0:
            self.parent.popupServerMessage("Energy change must be less than 10 ev")
            return
        else:
            comm_s = 'mvaDescriptor("energy",' + str(self.energy_ledit.text()) + ")"
            logger.info(comm_s)
            self.parent.send_to_server(comm_s)

    def beamSizeChangedCB(self, value=None, char_value=None, **kw):
        self.beamsize_combo_box.setCurrentIndex(value)

    def setTransCB(self):
        try:
            if (
                float(self.transmission_ledit.text()) > 1.0
                or float(self.transmission_ledit.text()) < 0.001
            ):
                self.parent.popupServerMessage("Transmission must be 0.001-1.0")
                return
        except ValueError as e:
            self.parent.popupServerMessage("Please enter a valid number")
            return
        comm_s = "setTrans(" + str(self.transmission_ledit.text()) + ")"
        logger.info(comm_s)
        self.parent.send_to_server(comm_s)

    def calcLifetimeCB(self):
        if not os.path.exists("2vb1.pdb"):
            os.system("cp -a $CONFIGDIR/2vb1.pdb .")
            os.system("mkdir rd3d")

        energyReadback = self.energy_pv.get() / 1000.0
        sampleFlux = self.sampleFluxPV.get()
        if hasattr(self, "transmission_ledit") and hasattr(
            self, "transmission_readback_label"
        ):
            try:
                sampleFlux = (
                    sampleFlux * float(self.transmission_ledit.text())
                ) / float(self.transmission_readback_label.text())
            except Exception as e:
                logger.info(f"Exception while calculating sample flux {e}")
        logger.info("sample flux = " + str(sampleFlux))
        try:
            vecLen_s = self.vecLenLabelOutput.text()
            if vecLen_s != "---":
                vecLen = float(vecLen_s)
            else:
                vecLen = 0
        except:
            vecLen = 0
        wedge = float(self.osc_range_ledit.text())
        try:
            raddose_thread = RaddoseThread(
                parent=self,
                beamsizeV=3.0,
                beamsizeH=5.0,
                vectorL=vecLen,
                energy=energyReadback,
                wedge=wedge,
                flux=sampleFlux,
                verbose=True,
            )
            raddose_thread.lifetime.connect(
                lambda lifetime: self.setLifetimeCB(lifetime)
            )
            raddose_thread.start()

        except:
            lifeTime_s = "0.00"

    def beamsizeComboActivatedCB(self, text):
        comm_s = 'set_beamsize("' + str(text[0:2]) + '","' + str(text[2:4]) + '")'
        logger.info(comm_s)
        self.parent.send_to_server(comm_s)

    def stillModeUserPushCB(self, state):
        logger.info("still checkbox state " + str(state))
        if self.parent.controlEnabled():
            if state:
                self.stillMode_pv.put(1)
                self.setGuiValues({"osc_range": "0.0"})
            else:
                self.standardMode_pv.put(1)
        else:
            self.parent.popupServerMessage("You don't have control")
            if self.stillModeStatePV.get():
                self.stillModeCheckBox.setChecked(True)
            else:
                self.stillModeCheckBox.setChecked(False)

    def setLifetimeCB(self, lifetime):
        if hasattr(self, "sampleLifetimeReadback_ledit"):
            self.sample_lifetime_readback_ledit.setText(f"{lifetime:.2f}")
            self.sample_lifetime_readback_ledit.setStyleSheet("color : black")

    def protoRadioToggledCB(self, text):
        if self.protoStandardRadio.isChecked():
            self.protoComboBox.setCurrentIndex(self.protoComboBox.findText("standard"))
            self.protoComboActivatedCB(text)
        elif self.protoRasterRadio.isChecked():
            self.protoComboBox.setCurrentIndex(self.protoComboBox.findText("raster"))
            self.protoComboActivatedCB(text)
        elif self.protoVectorRadio.isChecked():
            self.protoComboBox.setCurrentIndex(self.protoComboBox.findText("vector"))
            self.protoComboActivatedCB(text)
        else:
            pass

    def protoComboActivatedCB(self, text):
        self.showProtParams()
        protocol = str(self.protoComboBox.currentText())
        if protocol in ("raster", "stepRaster", "rasterScreen", "multiCol"):
            self.parent.vidActionRasterDefRadio.setChecked(True)
        else:
            self.parent.vidActionC2CRadio.setChecked(True)
        if protocol == "burn":
            self.parent.staffScreenDialog.fastDPCheckBox.setChecked(False)
        else:
            self.parent.staffScreenDialog.fastDPCheckBox.setChecked(True)
        if protocol == "raster":
            self.protoRasterRadio.setChecked(True)
            self.osc_start_ledit.setEnabled(False)
            self.osc_range_ledit.setEnabled(False)
            self.setGuiValues(
                {
                    "osc_range": getBlConfig("rasterDefaultWidth"),
                    "exp_time": getBlConfig("rasterDefaultTime"),
                    "transmission": getBlConfig("rasterDefaultTrans"),
                }
            )
        elif protocol == "rasterScreen":
            self.osc_start_ledit.setEnabled(False)
            self.osc_range_ledit.setEnabled(False)
            self.setGuiValues(
                {
                    "osc_range": getBlConfig("rasterDefaultWidth"),
                    "exp_time": getBlConfig("rasterDefaultTime"),
                    "transmission": getBlConfig("rasterDefaultTrans"),
                }
            )
            self.protoOtherRadio.setChecked(True)
        elif protocol == "standard":
            self.protoStandardRadio.setChecked(True)
            self.setGuiValues(
                {
                    "osc_range": getBlConfig("screen_default_width"),
                    "exp_time": getBlConfig("screen_default_time"),
                    "transmission": getBlConfig("stdTrans"),
                }
            )
            self.osc_start_ledit.setEnabled(True)
            self.osc_range_ledit.setEnabled(True)
        elif protocol == "burn":
            self.setGuiValues(
                {
                    "osc_range": "0.0",
                    "exp_time": getBlConfig("burnDefaultTime"),
                    "transmission": getBlConfig("burnDefaultTrans"),
                }
            )
            screenWidth = float(getBlConfig("burnDefaultNumFrames"))
            self.setGuiValues({"osc_end": screenWidth})
            self.osc_start_ledit.setEnabled(True)
            self.osc_range_ledit.setEnabled(True)

        elif protocol == "vector":
            self.setGuiValues(
                {
                    "osc_range": getBlConfig("screen_default_width"),
                    "exp_time": getBlConfig("screen_default_time"),
                    "transmission": getBlConfig("stdTrans"),
                }
            )
            self.osc_start_ledit.setEnabled(True)
            self.osc_range_ledit.setEnabled(True)
            self.protoVectorRadio.setChecked(True)
        else:
            self.protoOtherRadio.setChecked(True)
        self.totalExpChanged("")

    def showProtParams(self):
        protocol = str(self.protoComboBox.currentText())
        self.rasterParamsFrame.hide()
        self.characterizeParamsFrame.hide()
        self.processingOptionsFrame.hide()
        self.multiColParamsFrame.hide()
        self.osc_start_ledit.setEnabled(True)
        self.osc_end_ledit.setEnabled(True)
        if protocol == "raster" or protocol == "rasterScreen":
            self.rasterParamsFrame.show()
            self.osc_start_ledit.setEnabled(False)
            self.osc_end_ledit.setEnabled(False)

        elif protocol == "stepRaster":
            self.rasterParamsFrame.show()
            self.processingOptionsFrame.show()
        elif protocol == "multiCol" or protocol == "multiColQ":
            self.rasterParamsFrame.show()
            self.osc_start_ledit.setEnabled(False)
            self.osc_end_ledit.setEnabled(False)
            self.multiColParamsFrame.show()
        elif protocol == "vector" or protocol == "stepVector":
            self.vectorParamsFrame.show()
            self.processingOptionsFrame.show()
        elif protocol == "characterize" or protocol == "ednaCol":
            self.characterizeParamsFrame.show()
            self.processingOptionsFrame.show()
        elif protocol == "standard" or protocol == "burn":
            self.processingOptionsFrame.show()
        else:
            pass
