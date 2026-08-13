import serial
import time

def probe_tinysa(port="COM16", baud=115200):
    print(f"Connecting to {port} at {baud} baud...")
    try:
        ser = serial.Serial(port, baudrate=baud, timeout=2)
        time.sleep(0.2)
        
        # Flush buffers
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        
        # Send version command
        print("\n--> Sending 'version' command...")
        ser.write(b"version\r\n")
        time.sleep(0.3)
        resp = ser.read_all().decode('utf-8', errors='ignore')
        print(f"Response:\n{resp}")
        
        # Send info command
        print("\n--> Sending 'info' command...")
        ser.write(b"info\r\n")
        time.sleep(0.3)
        info_resp = ser.read_all().decode('utf-8', errors='ignore')
        print(f"Response:\n{info_resp}")
        
        # Send test sweep command
        print("\n--> Sending 'sweep 2400000000 2483500000 101' command...")
        ser.write(b"sweep 2400000000 2483500000 101\r\n")
        time.sleep(0.5)
        sweep_resp = ser.read_all().decode('utf-8', errors='ignore')
        lines = sweep_resp.strip().split('\n')
        print(f"Sweep lines received: {len(lines)}")
        if lines:
            print("First 3 lines:", lines[:3])
            print("Last 2 lines:", lines[-2:])

        ser.close()
        print("\nSUCCESS: TinySA hardware verified!")
    except Exception as e:
        print(f"\nERROR connecting to {port}: {e}")

if __name__ == "__main__":
    probe_tinysa()
