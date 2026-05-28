import pyvisa
import time
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
from datetime import datetime

# --- HARDWARE CONFIGURATION ---
B2985B_ADDR = 'GPIB0::23::INSTR'   # Electrometer

# --- EXPERIMENT PARAMETERS ---
PULSE_VOLTAGE = 2.5        # Stimulation Voltage (Write)
READ_VOLTAGE  = 0.2        # Inference Voltage (Read)
PULSE_WIDTH   = 0.02       # Duration of High Pulse (s)

INTER_TRAIN_DELAY = 1.0

# Neuromorphic Variables
DELTA_T_LIST = 30 * [0.4]  
PULSES_PER_BURST = 10      

# Hardware Timing Engine
BASE_TIME_STEP = 0.02  # 20 ms fixed hardware interval per point

# --- DYNAMIC FILENAME GENERATION ---
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
OUTPUT_FILENAME = f"Neuromorphic_Keysight_HWTimed_{timestamp}_{PULSE_VOLTAGE}V_{PULSE_WIDTH}s.xlsx"

def check_error(inst, context=""):
    """Fetches and prints any SCPI errors from the instrument."""
    err = inst.query(":SYST:ERR?").strip()
    if '+0,"No error"' not in err and '0,"No error"' not in err:
        print(f"SCPI Error [{context}]: {err}")

def init_instruments():
    rm = pyvisa.ResourceManager()
    b2985 = rm.open_resource(B2985B_ADDR)
    
    b2985.timeout = 10000 
    
    b2985.write("*RST")
    b2985.write(":SENS:FUNC 'CURR'")
    b2985.write(":SENS:CURR:RANG:AUTO ON") 
    b2985.write(":SENS:CURR:NPLC 0.01")      
    
    b2985.write(":SOUR:FUNC VOLT")           
    b2985.write(":SOUR:VOLT:RANG 10")        
    b2985.write(":FORM:ELEM:SENS CURR,TIME,SOUR") 
    
    check_error(b2985, "Post-Initialization Setup")
    print(f"B2985B: {b2985.query('*IDN?').strip()}")
    return b2985

def run_experiment():
    b2985 = init_instruments()
    
    try:
        print(f"Generating Hardware Waveform ({BASE_TIME_STEP*1000:.0f}ms steps)...")
        volt_list = []
        analysis_markers = []
        
        # We will store the exact indices where perform_measurement() would have happened
        meas_indices = []
        
        # --- DIGITIZE THE WAVEFORM ---
        for dt in DELTA_T_LIST:
            # A. Baseline Read (0.2s)
            pts_base = int(round(0.2 / BASE_TIME_STEP))
            volt_list.extend([READ_VOLTAGE] * pts_base)
            
            # 1st Measurement: Right before the pulse train begins
            init_idx = len(volt_list) - 1 
            meas_indices.append(init_idx)
            
            # B. Apply Pulse Train
            for p in range(PULSES_PER_BURST):
                # High Pulse
                pts_high = int(round(PULSE_WIDTH / BASE_TIME_STEP))
                volt_list.extend([PULSE_VOLTAGE] * pts_high)
                
                # Low/Read state
                pts_low = int(round(dt / BASE_TIME_STEP))
                
                # Intermediate Measurement
                meas_idx = len(volt_list) + 1 
                if pts_low < 2: meas_idx = len(volt_list) # safety fallback
                meas_indices.append(meas_idx)
                
                volt_list.extend([READ_VOLTAGE] * pts_low)
            
            # C. Post-Train Read (0.2s)
            pts_post = int(round(0.2 / BASE_TIME_STEP))
            volt_list.extend([READ_VOLTAGE] * pts_post)
            
            # Final Measurement: Right at the end of the post-read
            final_idx = len(volt_list) - 1 
            meas_indices.append(final_idx)
            
            # D. Wait Period
            pts_wait = int(round(INTER_TRAIN_DELAY / BASE_TIME_STEP))
            volt_list.extend([READ_VOLTAGE] * pts_wait)
            
            analysis_markers.append({
                'dt': dt,
                'init_idx': init_idx,
                'final_idx': final_idx
            })

        total_points = len(volt_list)
        total_time = total_points * BASE_TIME_STEP
        
        # --- LOAD WAVEFORM INTO B2985B ---
        volt_str = ",".join(f"{v:.1f}" for v in volt_list)
        b2985.write(":SOUR:VOLT:MODE LIST")
        b2985.write(f":SOUR:LIST:VOLT {volt_str}")
        check_error(b2985, "List Load")
        
        # --- CONFIGURE TRACE BUFFER ---
        b2985.write(":TRAC:CLE")
        b2985.write(f":TRAC:POIN {total_points}")
        b2985.write(":TRAC:FEED SENS")
        b2985.write(":TRAC:FEED:CONT NEXT")
        
        # --- CONFIGURE TRIGGER ENGINE ---
        b2985.write(":TRIG:SOUR TIM")         
        b2985.write(f":TRIG:TIM {BASE_TIME_STEP}")  
        b2985.write(f":TRIG:COUN {total_points}")
        b2985.write(":ARM:SOUR IMM")
        b2985.write(":ARM:COUN 1")
        check_error(b2985, "Trigger Config")

        print(f"Starting deterministic execution: {total_points} points (~{total_time:.1f} sec)")
        b2985.write(":OUTP ON")
        b2985.write(":INP ON")
        b2985.write(":INIT")
        
        # Sleep PC while instrument runs independently
        time.sleep(total_time + 1.0)
        
        b2985.write(":OUTP OFF")
        b2985.write(":INP OFF")
        
        # --- FETCH ALL DATA ---
        print("Experiment completed. Fetching trace data...")
        raw_data = b2985.query(":TRAC:DATA?").strip().split(',')
        
        vals = np.array([float(x) for x in raw_data])
        raw_trace_current = vals[0::3]
        raw_trace_time    = vals[1::3]
        raw_trace_voltage = vals[2::3]
        
        # Base resistance calculation
        raw_trace_resistance = np.where(
            np.abs(raw_trace_current) > 1e-12, 
            np.abs(raw_trace_voltage / raw_trace_current), 
            np.nan
        )

        # -------------------------------------------------------------------
        # NEW LOGIC: Extract True Hardware Pulse Timings
        # -------------------------------------------------------------------
        print("Calculating True Hardware Pulse Timings...")
        pulse_records = []
        
        # Identify where voltage transitions to PULSE_VOLTAGE and back down
        is_high = raw_trace_voltage > (PULSE_VOLTAGE * 0.5)
        transitions = np.diff(is_high.astype(int))
        
        rise_indices = np.where(transitions == 1)[0] + 1
        fall_indices = np.where(transitions == -1)[0] + 1
        
        for i in range(min(len(rise_indices), len(fall_indices))):
            t_rise = raw_trace_time[rise_indices[i]]
            t_fall = raw_trace_time[fall_indices[i]]
            actual_pw = t_fall - t_rise
            
            # Calculate time between this pulse dropping and the next pulse rising
            if i + 1 < len(rise_indices):
                t_next_rise = raw_trace_time[rise_indices[i+1]]
                actual_off = t_next_rise - t_fall
            else:
                actual_off = np.nan # Last pulse in the dataset has no "next" pulse
                
            pulse_records.append({
                'Pulse_Number': i + 1,
                'Time_Rise (s)': t_rise,
                'Time_Fall (s)': t_fall,
                'Actual_Pulse_Width (s)': actual_pw,
                'Actual_Off_Time (s)': actual_off
            })

        if pulse_records:
            print(f"Verified: Pulse 1 Width was {pulse_records[0]['Actual_Pulse_Width (s)'] * 1000:.1f} ms")
        
        # -------------------------------------------------------------------
        # Filter Resistance Data to match old software measurements
        # -------------------------------------------------------------------
        sparse_resistance = np.full_like(raw_trace_resistance, np.nan)
        valid_indices = [i for i in meas_indices if i < len(raw_trace_resistance)]
        sparse_resistance[valid_indices] = raw_trace_resistance[valid_indices]

        # --- EXTRACT LTP DATA ---
        results_summary = []
        for i, marker in enumerate(analysis_markers):
            idx_i = marker['init_idx']
            idx_f = marker['final_idx']
            
            r_initial = raw_trace_resistance[idx_i] if idx_i < len(raw_trace_resistance) else np.nan
            r_final = raw_trace_resistance[idx_f] if idx_f < len(raw_trace_resistance) else np.nan
            
            if not np.isnan(r_initial) and not np.isnan(r_final) and r_initial != 0:
                delta_r_percent = ((r_final - r_initial) / r_initial) * 100
            else:
                delta_r_percent = 0
                
            print(f"Train {i+1} | dt: {marker['dt']}s | R_init: {r_initial:.2e} Ω | R_final: {r_final:.2e} Ω | Change: {delta_r_percent:.2f}%")
            
            results_summary.append({
                'Delta_t (s)': marker['dt'],
                'R_Initial': r_initial,
                'R_Final': r_final,
                'Change_Percent': delta_r_percent
            })

        save_and_plot(raw_trace_time, raw_trace_voltage, raw_trace_current, sparse_resistance, results_summary, pulse_records)

    except Exception as e:
        print(f"Experiment Error: {e}")
        
    finally:
        b2985.write(":OUTP OFF")
        b2985.write(":SOUR:VOLT 0")
        b2985.close()

def save_and_plot(time_data, volt_data, curr_data, res_data, results_summary, pulse_records):
    df_trace = pd.DataFrame({
        'Time (s)': time_data,
        'Voltage (V)': volt_data,
        'Current (A)': curr_data,
        'Resistance (Ohm)': res_data
    })
    
    df_summary = pd.DataFrame(results_summary)
    df_pulses = pd.DataFrame(pulse_records)  # <--- NEW Dataframe for Pulse Timings
    
    with pd.ExcelWriter(OUTPUT_FILENAME) as writer:
        df_trace.to_excel(writer, sheet_name='Raw_Trace', index=False)
        df_summary.to_excel(writer, sheet_name='Summary', index=False)
        df_pulses.to_excel(writer, sheet_name='Pulse_Timings', index=False) # <--- Save to Excel
    print(f"Files saved to {OUTPUT_FILENAME}")

 

    # --- PLOTTING ---
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 12))
    
    # Plot 1: Actual Waveform (Square Step Plot - Fully detailed)
    ax1.step(df_trace['Time (s)'], df_trace['Voltage (V)'], where='post', color='tab:blue', linewidth=0.8)
    ax1.set_ylabel('Voltage (V)')
    ax1.set_title(f'Hardware-Timed Waveform (File: {OUTPUT_FILENAME})')
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim(0, PULSE_VOLTAGE * 1.1)
    
    # Plot 2: Resistance Response (Drops NaNs, restoring the clean red circles)
    df_clean = df_trace.dropna(subset=['Resistance (Ohm)'])
    ax2.plot(df_clean['Time (s)'], df_clean['Resistance (Ohm)'], 'r-o', markersize=3, linewidth=1)
    ax2.set_ylabel('Resistance ($\Omega$)')
    ax2.set_yscale('log')
    ax2.set_title('Resistance Evolution (Measured after each pulse)')
    ax2.grid(True, which="both", alpha=0.3)
    
    # Plot 3: Rate Coding Curve
    ax3.plot(df_summary['Delta_t (s)'], df_summary['Change_Percent'], 'g-s', linewidth=2)
    ax3.set_xlabel('Inter-Pulse Interval $\Delta t$ (s)')
    ax3.set_ylabel('Synaptic Weight Change (%)')
    ax3.set_title('LTP behaviour')
    ax3.axhline(0, color='black', linewidth=1)
    ax3.grid(True, alpha=0.5)
    
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    run_experiment()
