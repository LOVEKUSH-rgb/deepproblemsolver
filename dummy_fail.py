# A dummy script that deliberately fails to test CI
import math

def calculate_magic():
    return 1 / math.fabs(-0)

if __name__ == "__main__":
    calculate_magic()
