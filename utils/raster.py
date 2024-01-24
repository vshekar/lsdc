import numpy as np


def calculate_matrix_index(k, M, N, pattern="horizontal"):
    if pattern=="horizontal":
        i = k // N
        if i % 2 == 0: # odd row
            j= k - (i*N)
        else:
            j = N - (k - (i*N)) - 1
        return i, j
    elif pattern == "vertical":
        j= k // M
        if j % 2 == 0: # odd column
            i = k - (j*M)
        else:
            i= M - (k - (j*M)) - 1
        return i, j


def calculate_flattened_index(i, j, M, N, pattern='horizontal'):
    if pattern == 'horizontal':
        if i % 2 == 0:  # odd row
            return i * (N) +  j 
        else:  # even row
            return i * N + (N - 1 - j)
    elif pattern == 'vertical':
        if j % 2 == 0:  # Odd column
            return j * M + i
        else:  # Even column
            return j * M + (M - 1 - i)
    else:
        raise ValueError("Invalid pattern specified")


def create_snake_array(flattened, raster_type, M, N):
    # Reshape the list to a 2D array
    array_2d = np.array(flattened).reshape(M, N)

    
    if raster_type == 'horizontal':
        # Reverse every even row for horizontal snaking
        array_2d[1::2] = np.fliplr(array_2d[1::2])
    elif raster_type == 'vertical':
        # Reverse every odd column for vertical snaking
        array_2d = array_2d.T
        array_2d[:, 0::2] = np.flipud(array_2d[:, 0::2])
    
    return array_2d

def determine_raster_shape(raster_def):
    if (raster_def["rowDefs"][0]["start"]["y"]
        == raster_def["rowDefs"][0]["end"]["y"]
    ):  # this is a horizontal raster
        raster_dir = "horizontal"
    else:
        raster_dir = "vertical"

    
    num_rows = len(raster_def["rowDefs"])
    num_cols = raster_def["rowDefs"][0]["numsteps"]
    if raster_dir == "vertical":
        num_rows, num_cols = num_cols, num_rows

    return raster_dir, num_rows, num_cols


def get_raster_max_col(raster_def, max_index):
    """
    Given the results of a snake raster return a matrix of the 
    desired metric. The numpy array returned will have M rows and N columns
    regardless of how the data was collected
    """
    raster_dir, num_rows, num_cols = determine_raster_shape(raster_def)
    i, j = calculate_matrix_index(max_index, num_rows, num_cols, pattern=raster_dir)

    return j

    

def get_flattened_indices_of_max_col(raster_def, max_col):
    """
    Given a column in a 2d raster this function returns the indices of all elements
    in the column in the flattened list
    """
    raster_dir, num_rows, num_cols = determine_raster_shape(raster_def)

    indices = []
    j = max_col
    for i in range(num_rows):
        indices.append(calculate_flattened_index(i, j, num_rows, num_cols, pattern=raster_dir))

    return indices