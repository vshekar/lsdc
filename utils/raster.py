import numpy as np


def calculate_matrix_index(k, M, N, pattern="horizontal"):
    """
    Returns the row and column index in a raster based on the
    index of the result array, shape of the raster and the
    direction of collection
    """
    if pattern == "horizontal":
        i = k // N
        if i % 2 == 0:  # odd row
            j = k - (i * N)
        else:
            j = N - (k - (i * N)) - 1
        return i, j
    elif pattern == "vertical":
        j = k // M
        if j % 2 == 0:  # odd column
            i = k - (j * M)
        else:
            i = M - (k - (j * M)) - 1
        return i, j


def calculate_flattened_index(y, x, num_cols, num_rows, pattern: "Optional[str]"="horizontal"):
    """
    Returns the index of the result array of a raster based on the
    row and column index, shape of the raster and the
    direction of collection
    If pattern = None, snaking pattern is not used. Rows are arranged
    left to right
    """
    if pattern == "horizontal":
        if y % 2 == 0:  # odd row
            return y * (num_rows) + x
        else:  # even row
            return y * num_rows + (num_rows - 1 - x)
    elif pattern == "vertical":
        if x % 2 == 0:  # Odd column
            return x * num_cols + y
        else:  # Even column
            return x * num_cols + (num_cols - 1 - y)
    elif pattern is None:
        return y * num_rows + x
    else:
        raise ValueError("Invalid pattern specified")


def create_snake_array(flattened, raster_type, M, N):
    """
    Returns an MxN matrix of raster results given the
    flattened result array, direction, and shape of the raster
    """
    # Reshape the list to a 2D array
    if raster_type == "horizontal":
        # Reverse every even row for horizontal snaking
        array_2d = np.array(flattened).reshape(M, N)
        array_2d[1::2] = np.fliplr(array_2d[1::2])
    elif raster_type == "vertical":
        # Reverse every even column for vertical snaking
        array_2d = np.array(flattened).reshape(N, M)
        array_2d = array_2d.T
        array_2d[:, 1::2] = np.flipud(array_2d[:, 1::2])

    return array_2d


def determine_raster_shape(raster_def):
    """
    Returns the shape and direction of a raster given
    the raster definition
    """
    if (
        raster_def["rowDefs"][0]["start"]["y"] == raster_def["rowDefs"][0]["end"]["y"]
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
    Returns the column of the raster corresponding to the given
    index in the flattened array
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
        indices.append(
            calculate_flattened_index(i, j, num_rows, num_cols, pattern=raster_dir)
        )

    return indices


def peakfind_maxburn(array, num_iter):
    '''
    Collection center finding for multiCol protocol
    
    Input 2D array, find max element, store max index in list,
    then set max element and its 8 neighbors to zero (a.k.a. burn this spot)
    
    Repeat until all elements set to zero, or maximum number of iterations reached
    
    Returns center list, and "burnt" array
    '''
    arr_work = array.copy()
    indices = []
    iterate = 1
    while arr_work.max() != 0 and iterate <= num_iter:
        iterate = iterate + 1
        i, j = np.unravel_index(np.argmax(arr_work), arr_work.shape)
        indices.append((i, j))
        arr_work[max(i-1, 0):i+2, max(j-1, 0):j+2] = 0
    return indices, arr_work
