def process_data(data):
    if not isinstance(data, dict):
        raise TypeError("process_data expects a dictionary input!")
    return data.get("value", 0) * 2
