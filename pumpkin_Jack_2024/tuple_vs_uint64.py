
## Helper functions to convert animation frames from the online LED matrix editor
# https://xantorohara.github.io/led-matrix-editor/

## Convert Tuple to uint64_t
def tuple_to_uint64(frame_tuple):
    # Combine each byte (shifted appropriately) into a single 64-bit integer
    uint64_value = 0
    for i, byte in enumerate(frame_tuple):
        uint64_value |= byte << (8 * (7 - i))  # Shift the byte by the appropriate amount and combine
    return f"0x{uint64_value:016x}"  # Ensure that the output is always 16 hexadecimal digits long


## Convert uint64_t to Tuple
def uint64_to_tuple(uint64_value):
    # Extract each byte from the 64-bit integer and store it in a tuple
    frame_tuple = tuple((uint64_value >> (8 * (7 - i))) & 0xFF for i in range(8))
    return frame_tuple

## Mirror the matrix horizontally
# (reverse the bits in each byte)
def mirror_matrix_horizontally(matrix):
    def reverse_byte(byte):
        reversed_byte = 0
        for i in range(8):
            reversed_byte |= ((byte >> i) & 0x01) << (7 - i)
        return reversed_byte
    mirrored_matrix = tuple(tuple(hex(reverse_byte(byte)) for byte in row) for row in matrix)
    return mirrored_matrix



###### Example 

Frame1 = (0x00, 0xC0, 0xF8, 0x7F, 0x7F, 0x3F, 0x3E, 0x1C)
Frame2 = (0x00, 0x00, 0xF8, 0x7F, 0x7F, 0x3F, 0x3E, 0x1C)
Frame3 = (0x00, 0x00, 0xF8, 0x7F, 0x7F, 0x3F, 0x3E, 0x00)
Frame4 = (0x00, 0x00, 0x00, 0x7F, 0x7F, 0x3F, 0x00, 0x00)
Frame5 = (0x00, 0x00, 0x00, 0x00, 0x7F, 0x00, 0x00, 0x00)

# Convert tuple to uint64
uint64_value1 = tuple_to_uint64(Frame1)
uint64_value2 = tuple_to_uint64(Frame2)
uint64_value3 = tuple_to_uint64(Frame3)
uint64_value4 = tuple_to_uint64(Frame4)
uint64_value5 = tuple_to_uint64(Frame5)

print(f"{uint64_value1}")
print(f"{uint64_value2}")
print(f"{uint64_value3}")
print(f"{uint64_value4}")
print(f"{uint64_value5}")

## https://xantorohara.github.io/led-matrix-editor/#00c0f87f7f3f3e1c|0000f87f7f3f3e1c|0000f87f7f3f3e00|0000007f7f3f0000|000000007f000000
# const uint64_t IMAGES[] = {
#     0x00c0f87f7f3f3e1c,
#     0x0000f87f7f3f3e1c,
#     0x0000f87f7f3f3e00,
#     0x0000007f7f3f0000,
#     0x000000007f000000,
# };
# const int IMAGES_LEN = sizeof(IMAGES)/8;


## Convert uint64 back to tuple
# converted_tuple = uint64_to_tuple(uint64_value)
# print(f"Uint64 back to tuple: {converted_tuple}")


EV = (
    (0x00, 0xC0, 0xF8, 0x7F, 0x7F, 0x3F, 0x3E, 0x1C),
    (0x00, 0x00, 0xF8, 0x7F, 0x7F, 0x3F, 0x3E, 0x1C),
    (0x00, 0x00, 0xF8, 0x7F, 0x7F, 0x3F, 0x3E, 0x00),
    (0x00, 0x00, 0x00, 0x7F, 0x7F, 0x3F, 0x00, 0x00),
    (0x00, 0x00, 0x00, 0x00, 0x7F, 0x00, 0x00, 0x00),
)

EV_mirrored = mirror_matrix_horizontally(EV)

IFrame1 = (0x0, 0x3, 0x1f, 0xfe, 0xfe, 0xfc, 0x7c, 0x38)
IFrame2 = (0x0, 0x0, 0x1f, 0xfe, 0xfe, 0xfc, 0x7c, 0x38)
IFrame3 = (0x0, 0x0, 0x1f, 0xfe, 0xfe, 0xfc, 0x7c, 0x0)
IFrame4 = (0x0, 0x0, 0x0, 0xfe, 0xfe, 0xfc, 0x0, 0x0)
IFrame5 = (0x0, 0x0, 0x0, 0x0, 0xfe, 0x0, 0x0, 0x0)

uint64_value1i = tuple_to_uint64(IFrame1)
uint64_value2i = tuple_to_uint64(IFrame2)
uint64_value3i = tuple_to_uint64(IFrame3)
uint64_value4i = tuple_to_uint64(IFrame4)
uint64_value5i = tuple_to_uint64(IFrame5)

print(f"{uint64_value1i}")
print(f"{uint64_value2i}")
print(f"{uint64_value3i}")
print(f"{uint64_value4i}")
print(f"{uint64_value5i}")

# https://xantorohara.github.io/led-matrix-editor/#00031ffefefc7c38|00001ffefefc7c38|00001ffefefc7c00|000000fefefc0000|00000000fe000000
# const uint64_t IMAGES[] = {
#     0x00031ffefefc7c38,
#     0x00001ffefefc7c38,
#     0x00001ffefefc7c00,
#     0x000000fefefc0000,
#     0x00000000fe000000,
# };
# const int IMAGES_LEN = sizeof(IMAGES)/8;

