# -GE CONFIDENTIAL-
# Type: Source Code
#
# Copyright (c) 2024, GE Healthcare
# All Rights Reserved
#
# This unpublished material is proprietary to GE Healthcare. The methods and
# techniques described herein are considered trade secrets and/or
# confidential. Reproduction or distribution, in whole or in part, is
# forbidden except by express written permission of GE Healthcare.
#
# Script for parsing DRC fles generated with iCollect to trends and waveforms as CSV files
# 
# Example usage:
# to convert all DRC files in a folder to CSV format in the same folder
# > python drc_2_csv.py "C:\\localdbs\\Sample_drc_files"

# This code was generated with the assistance of GitHub Copilot and other GenAI tools.

import argparse
import csv
import numpy as np
import os
import pandas as pd
import struct
import warnings

from datetime import datetime, timezone

DRI_MAX_SUBRECS = 8
DATA_INVALID = -32760

TEST = 0    # set to 1 for testing with a single file section
if not(TEST):
    SKIP_RECORDS = 0
    MAX_RECORDS = 1000*1000   # prevent running too large input files and memory gets full prior to processing
                            # set to 1 million > 3 Days of data with 4 packages per seconds
    FILENAME = ""  #keep as empty string to get all files in current folder and subfolders.
    NO_WAVES = False
    NO_CSV = False
else:
    SKIP_RECORDS = 0
    MAX_RECORDS  = 1000  
    FILENAME = ""  # filter on end of filename before ".drc" for testing one or a few files only
    NO_WAVES = False
    NO_CSV = True

ECG12_TYPE_IDENTIFIER = 22  # Identifier for ECG12 packets

class VariableLogger:
    def __init__(self):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.filename = "drc_2_csv_" + timestamp + ".log"
        self.file_exists = os.path.exists(self.filename)
        
        # Open the file in append mode if it already exists
        self.file_mode = 'a' if self.file_exists else 'w'
        self.file_handle = open(self.filename, mode=self.file_mode, newline='')
        self.writer = csv.writer(self.file_handle)
        
        # Write header only if the file is newly created
        if not self.file_exists:
            self.writer.writerow(['Time', 'File Name', 'Variable Name', 'Value'])

    def set_filename(self, filename):
        self.filename = filename

    def log_variables(self, variables):
        # Write variable names and their values
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        for var_name, var_value in variables.items():
            self.writer.writerow([timestamp, self.filename, var_name, var_value])

    def close_file(self):
        self.file_handle.close()


def extract_integers_post_header(all_data, logger=None):
    trend_data = []
    wave_data = []
    times = []  # List to store converted times
    data_pointer = 0
    data_length = len(all_data)
    last_dri_level = 0
    header_struct_format = '< h b b H I b b H h ' + 'h b' * DRI_MAX_SUBRECS  # Adjusted for DRI_MAX_SUBRECS
    header_struct = struct.Struct(header_struct_format)
    cnt = 0
    readable_time = "no time"
    first_wave_time_unix = None
    previous_r_nbr = None
    gap_detected = 0

    pacer_info_list = []  # Temporary array to store pacer information
    pacer_time = 0
    pacer_timestamp = None  # Initialize pacer_timestamp to avoid UnboundLocalError

    while data_pointer < data_length:
        if cnt > MAX_RECORDS: #avoid too large files that may cause out of memory failure
            break

        header_data = all_data[data_pointer:data_pointer+40]
        data_pointer += 40
        if not header_data: # or len(header_data) != 40:
            break
        (r_len, r_nbr_signed, dri_level, plug_id, r_time, n_subnet, res, dest_plug_id, r_maintype, *sr_desc) = header_struct.unpack(header_data)
        r_nbr = r_nbr_signed & 0xFF  # Interpret r_nbr as an unsigned byte
        if (r_len < 0) or (r_len>5000):
            break
        if last_dri_level>0:
            if not (dri_level==last_dri_level):
                break
        last_dri_level = dri_level
            
        with warnings.catch_warnings():
            # Suppress the DeprecationWarning temporarily
            warnings.simplefilter("ignore")
            readable_time = datetime.utcfromtimestamp(r_time).replace(tzinfo=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            if first_wave_time_unix is None and r_maintype == 1:
                first_wave_time_unix = r_time

        raw_sr_offset = sr_desc[::2]  # Extract even-indexed elements
        raw_sr_type = [0 if t < -1 or t > 50 else t for t in sr_desc[1::2]]   # Set values not in range 0..5 to zero
        sr_offset = [0 if t == 0 else offset for offset, t in zip(raw_sr_offset, raw_sr_type)]  # Adjust sr_offset
        sr_cnt = sum(1 for tpe in raw_sr_type if tpe > 0)
        cnt +=1
        record_len = r_len - 40
        if (cnt > SKIP_RECORDS):
            if r_maintype == 0: #trends
                if sr_cnt > 4:
                    sr_cnt = 4
                sr_type = raw_sr_type[:sr_cnt]
                sr_offset = raw_sr_offset[:sr_cnt]
    
                phdb_bytes = all_data[data_pointer:data_pointer+record_len]
                if len(phdb_bytes) < record_len:
                    break
    
                #split in list of integers by sr_offset
                subrecs = []
                for ndx in range(len(sr_offset)):
                    offset = sr_offset[ndx]
                    data_bytes = phdb_bytes[offset:offset+279]
                    if len(data_bytes)>277:  
                        subrecord = data_bytes[4:274]
                        subrecord_len = len(subrecord)
                        subrecord_integers = [int.from_bytes(subrecord[i:i+2], byteorder='little', signed=True)
                                    for i in range(0, subrecord_len, 2)]
                        subrec_group = data_bytes[277] & 0x1F
                        subrecs.append([subrec_group, subrecord_integers])
                   
                trend_data.append(subrecs)
                times.append(readable_time)  # Append converted time
            elif (r_maintype == 1) and not NO_WAVES: #waveforms
                if sr_cnt > 8:
                    sr_cnt = 8
                sr_type = raw_sr_type[:sr_cnt]
                sr_offset = raw_sr_offset[:sr_cnt]
    
                data_bytes = all_data[data_pointer:data_pointer+record_len]
    
                if len(data_bytes) < record_len:
                    break            
                # Assuming data_bytes is your bytes object
                # Convert the entire data_bytes to a NumPy array of 16-bit signed integers
                data_np_array = np.frombuffer(data_bytes, dtype='<i2')  # '<i2' is little-endian 16-bit signed integer
                
                # Now, you can slice data_np_array using offsets and lengths as needed
                if wave_data == []:
                    if logger:
                        logger.log_variables({"FirstWaveTime": readable_time })

                if previous_r_nbr is not None:
                    r_diff = r_nbr - previous_r_nbr
                    if (abs(r_diff) > 1 and abs(r_diff) != 255):
                        if logger:
                            logger.log_variables({"GapTime": readable_time, "PacerTime": pacer_timestamp, "GapRecordNumber": r_nbr , "GapCount": r_diff - 1 })
                        print({"GapTime": readable_time, "PacerTime": pacer_timestamp, "GapRecordNumber": r_nbr , "GapCount": r_diff - 1 })
                        gap_detected = 1
                        

                subrecs= []
                for ndx in range(len(sr_offset)):
                    if (sr_type[ndx] <= 0) and (ndx > 0):
                        break
                    else:
                        offset = sr_offset[ndx] + 6
                        if ndx < sr_cnt - 1:
                            sr_end = sr_offset[ndx + 1]
                        else:
                            sr_end = record_len
                        
                        # Calculate start and end indices for the numpy array slice
                        start_idx = offset // 2  # Divide by 2 because each integer is 2 bytes
                        end_idx = sr_end // 2
                    
                        # Slice the NumPy array to get the subrecord
                        subrecord_np_array = data_np_array[start_idx:end_idx]
                    
                        # Append the subrecord array and its type to subrecs
                        if sr_type[ndx] != ECG12_TYPE_IDENTIFIER:           
                            subrecs.append([sr_type[ndx], subrecord_np_array])
                        else: # Recognize and process ECG12
                            block_size = 28*2  # Block size for ECG12
                            rollover_limit = 8000  # Counter rolls over every 8000 steps (80 seconds)
                            counter_prev = None

                            # Process all 28*2-byte blocks, skip first 10*2 (subheaders?)
                            for block_start in range(10*2, len(subrecord_np_array) * 2 + 10*2, block_size):
                                block = data_bytes[block_start:block_start + block_size]
                                if len(block) < block_size:
                                    break  # Avoid incomplete blocks

                                # Decode the second last 16-bit field (27th "sample")
                                last_field = int.from_bytes(block[52:54], byteorder='little')
                                pacer_info = (last_field >> 13) & 0b111  # Extract bits 15–13 for pacer
                                counter = last_field & 0x1FFF  # Extract bits 12–0 for counter

                                # Detect counter discontinuity (packet reordering or rollover)
                                if counter_prev is not None:
                                    if counter < counter_prev:  # Possible rollover or reordering
                                        if (counter_prev - counter) > rollover_limit // 2:
                                            pacer_time += (rollover_limit * 0.01)  # Add 80 seconds
                                        else:
                                            print(f"Warning: Packet reordering detected (Counter: {counter}, Last: {counter_prev})")
                                counter_prev = counter

                                # Calculate timestamp using counter and pacer bits
                                pacer_timestamp = pacer_time + (counter * 0.01)

                                if pacer_info > 0:
                                    # Add 2ms precision using pacer bits
                                    pacer_timestamp += (pacer_info - 1) * (0.01 / 5) - 0.01

                                pacer_timestamp_ms = (pacer_timestamp)*1000.0

                                if pacer_info != 0:
                                    pacer_info_list.append([
                                        f"{pacer_timestamp_ms:.6f}", "1", "1000", "1000", f"{gap_detected:1d}", "", "",
                                        "", "", "", "", "", "", "", "", ""
                                    ])
                                    gap_detected = 0
                wave_data.append(subrecs)

                previous_r_nbr = r_nbr
        remaining_bytes = r_len - 40
        data_pointer += remaining_bytes  # Adjust pointer to skip over remaining bytes
    if logger:
        logger.log_variables({"LastTime": readable_time, "PackageCount": cnt })
    return trend_data, times, wave_data, first_wave_time_unix, pacer_info_list  # Return times, first_wave_time_unix, and pacer_info_list along with data

def read_params_file(params_file_path):
    """
    Reads the parameter configuration file.
    """
    params_labels = ["Sel", "Gr", "Pos", "Div", "Name", "Unit", "Description"]
    return pd.read_csv(params_file_path, sep='\t', names=params_labels, header=None)
def read_waves_file(params_file_path):
    """
    Reads the parameter configuration file.
    """
    params_labels = ["Sel", "Freq","Delay","Divider","Filter","Column","Unit","Description"]
    return pd.read_csv(params_file_path, sep='\t', names=params_labels, header=None)

def process_drc_file(data_file_path, params_df, waves_df, logger=None):
    """
    Processes a single .drc file.
    """
    all_data = b''
    with open(data_file_path, 'rb') as file:
        all_data = file.read()
    trend_records, times, wave_records, first_wave_time_unix, pacer_info_list = extract_integers_post_header(all_data, logger)
    trend_df = generate_dataframe(trend_records, times, params_df, logger)
    waves_df, freq = generate_waves_dataframe(wave_records, waves_df, first_wave_time_unix, logger)
    return trend_df, waves_df, freq, pacer_info_list

def generate_waves_dataframe(all_records, params_df, first_wave_time_unix, logger=None):
    """
    Generates a dataframe from processed .drc data and parameter configuration.
    """
    df_config_len = len(params_df)
    label_list = params_df["Column"]
    # Initialize a list to keep track of groups that have data
    groups_with_data = [False] * df_config_len
    for record in all_records:
        for subrecord in record:
            group, integers = subrecord
            if len(integers)>1:
                groups_with_data[group] = True
    # Find group numbers with data
    group_numbers_with_data = [ndx for ndx, has_data in enumerate(groups_with_data) if has_data]
    if len(group_numbers_with_data) == 0:
        return None, 0
    filtered_labels = []
    concatenated_records = []
    # Collect labels from groups with data

    group_numbers_from_zero = []

    for group in group_numbers_with_data:
        if (group > 0) and (group < 50):
            group_number_from_zero = group - 1
            group_labels = label_list[group_number_from_zero]
            filtered_labels.append(group_labels)
            group_numbers_from_zero.append(group_number_from_zero)
            
            #TODO pick here not from new_records (missing group number), but from all_records 
            group_waveforms = []
               
            # Iterate over all records to find waveforms for the current group
            for record in all_records:
                for subrecord in record:
                    record_group, integers = subrecord
                    if record_group == group:
                        group_waveforms.append(integers)
                        break  # No need to continue searching in subsequent records
                    
            # Concatenate waveforms for the current group
            if group_waveforms:
                grouped_waveform = np.concatenate(group_waveforms, axis=0)
                concatenated_records.append(grouped_waveform)


    # Assuming params_df["Freq"] and group_numbers_with_data are defined and appropriate for your context
    freq_list = params_df["Freq"][group_numbers_from_zero]
    max_freq = max(freq_list)
    if logger:
        logger.log_variables({"max_freq": max_freq, "filtered_labels": filtered_labels })
 
    ratios = (max_freq // freq_list).tolist()
    
    stretched_records = []
    # Use enumerate for more Pythonic iteration over ratios and records
    max_size = 0
    for cnt, record in enumerate(concatenated_records):
        ratio = ratios[cnt]
        # Use np.repeat to stretch the record according to the ratio
        stretched_record = np.repeat(record, ratio)
        record_len = len(stretched_record)
        if (record_len > max_size):
            max_size = record_len
        stretched_records.append(stretched_record)

    padded_records = []
    # if come records are a bit shorter as the longest clamp
    for record in stretched_records:
        record_len = len(record)
        if (record_len < max_size):
            if (record_len > 3*max_size//4):
             # Pad the record to the end with zeros to match max_size
                pad_length = max_size - record_len
                record = np.pad(record, (0, pad_length), mode='constant')
        padded_records.append(record)
    
    # Filter out records that are not long enough if necessary
    
    final_record = []
    new_filtered_labels = []
    cnt = 0
    for record in padded_records:
        if (record.size == max_size):           
            final_record.append(record)
            filtered_label = filtered_labels[cnt]
            new_filtered_labels.append(filtered_label)
        cnt += 1

            
    concatenated_stretched_records = list(zip(*final_record))      
    new_record_df = pd.DataFrame(concatenated_stretched_records, columns=new_filtered_labels)

    # Pandas 3.x can raise on float assignment into integer dtypes.
    for col_name in new_record_df.columns[1:]:
        new_record_df[col_name] = new_record_df[col_name].astype("float64")
    
    for col_name in new_record_df.columns[1:]:
        divisor = params_df[params_df['Column'] == col_name]['Divider'].values[0]
        for i in range(len(new_record_df[col_name])):
            if new_record_df[col_name][i] > DATA_INVALID:
                new_record_df.at[i, col_name] = float(new_record_df[col_name][i]) / divisor

    # Add time column in Unix format with millisecond resolution
    if first_wave_time_unix is not None:
        time_column = np.arange(len(new_record_df)) / max_freq + first_wave_time_unix
        new_record_df.insert(0, 'Time', time_column)
        new_record_df['UnixTime'] = new_record_df['Time'].map(lambda x: f"{x:.4f}")

    return new_record_df.astype({col: 'float64' for col in new_record_df.columns[1:]}), max_freq

def generate_dataframe(all_records, times, params_df, logger=None):
    """
    Generates a dataframe from processed .drc data and parameter configuration.
    """
    df_config_len = len(params_df)
    # Create empty lists to store positions and labels for each group
    pos_list = [[] for _ in range(4)]
    label_list = [[] for _ in range(4)]
    # Fill in pos_list and label_list
    for ndx in range(df_config_len):
        this_pos = params_df["Pos"].iloc[ndx]
        this_label = params_df["Name"].iloc[ndx]
        this_group = params_df["Gr"].iloc[ndx]
        if this_pos < 136:  #basic/ext1..3 have 270 bytes, so 135 is maximum integer
            if not (this_pos in pos_list[this_group]): # do not add duplicates for masked values
                pos_list[this_group].append(this_pos)
                label_list[this_group].append(this_label)
    # Initialize a list to keep track of groups that have data
    group_with_data_len = 4
    groups_with_data = [False] * group_with_data_len
    new_records = []

    for record in all_records:
        new_record = []
        record_with_data = [False] * group_with_data_len
        
        for subrecord in record:
            group, integers = subrecord
            if group < group_with_data_len:
                if not record_with_data[group]: #skip duplicates
                    pos_indices = pos_list[group]
                    # Mark the group as having data
                    groups_with_data[group] = True
                    filtered_record = [integers[pos] if pos < len(integers) else 0 for pos in pos_indices]
                    new_record.extend(filtered_record)
                record_with_data[group] = True  
        new_records.append(new_record)
    # Find group numbers with data
    group_numbers_with_data = [ndx for ndx, has_data in enumerate(groups_with_data) if has_data]
    filtered_labels = []
    # Collect labels from groups with data
    for ndx in group_numbers_with_data:
        group_labels = label_list[ndx]
        filtered_labels.extend(group_labels)
    if len(times)>1:
        if logger:
            logger.log_variables({"FirstTrendTime": times[0], "SecondTrendTime": times[1], "LastTrendTime": times[-1] })
       
    new_record_df = pd.DataFrame(new_records, columns=filtered_labels)
    new_record_df.insert(0, 'Time', times)
    if len(times) > 1:
        for col_name in new_record_df.columns[1:]:
            divisor = params_df[params_df['Name'] == col_name]['Div'].values[0]
            for i in range(len(new_record_df[col_name])):
                try:
                    if new_record_df[col_name].iloc[i] > DATA_INVALID:
                        new_record_df[col_name] = new_record_df[col_name].astype(float)
                        new_record_df.at[i, col_name] = new_record_df[col_name].iloc[i] / divisor
                except Exception as e:
                    TempError = e
    
        new_record_df = new_record_df.loc[:, (new_record_df != new_record_df.iloc[0]).any()]
    return new_record_df.astype({col: 'float64' for col in new_record_df.columns[1:]})

def save_dataframe_to_csv(dataframe, output_file_path, logger=None):
    """
    Saves the dataframe to a CSV file.
    """
    if logger:
        logger.log_variables(dataframe.median(axis=0, numeric_only=True))
    
    if NO_CSV: 
        return
    
    with open(output_file_path, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        
        # Get first_wave_time_unix and freq from the dataframe
        if 'UnixTime' in dataframe.columns:
            first_wave_time_unix = float(dataframe['UnixTime'].iloc[0])
            last_wave_time_unix = float(dataframe['UnixTime'].iloc[-1])
            num_rows = len(dataframe)
            if num_rows > 1:
                avg_time_diff = (last_wave_time_unix - first_wave_time_unix) / (num_rows - 1)
                if avg_time_diff > 0:
                    freq = round(1 / avg_time_diff)
                else:
                    freq = 0
            else:
                freq = 0
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                datetime_str = datetime.utcfromtimestamp(first_wave_time_unix).strftime('%d/%m/%Y %H.%M.%S')
            writer.writerow([datetime_str, freq, f"{first_wave_time_unix:.0f}", os.path.basename(output_file_path)[:-10]])
        
        # Change UnixTime to strings with 4 decimal resolution and use Time as the header
        if 'UnixTime' in dataframe.columns:
            dataframe['Time'] = dataframe['UnixTime']
            dataframe.drop(columns=['UnixTime'], inplace=True)
        
        # Write the dataframe to the CSV file
        dataframe.to_csv(csvfile, index=False)
    
    print(f"DataFrame saved to: {output_file_path}")

def save_dataframe_to_mit(dataframe, output_file_path, freq):
    #TODO mit file writing to be implemented
    print #(f"DataFrame saved to: {output_file_path}")  

# GenAI generated code start
def save_pacers_to_csv(pacer_info_list, data_file_path):
    """
    Saves pacer information to a CSV file.
    """
    if NO_CSV: 
        return

    pacer_file_path = data_file_path.replace('.drc', '_pacers.csv')
    
    with open(pacer_file_path, mode='w', newline='') as pacer_file:
        pacer_writer = csv.writer(pacer_file)
        pacer_writer.writerow([
            "Timestamp", "Ch1-lead-polarity", "Ch1-amplitude", "Ch1-width",
            "Ch2-lead-polarity", "Ch2-amplitude", "Ch2-width",
            "Ch3-lead-polarity", "Ch3-amplitude", "Ch3-width",
            "Ch4-lead-polarity", "Ch4-amplitude", "Ch4-width",
            "Ch5-lead-polarity", "Ch5-amplitude", "Ch5-width"
        ])
        pacer_writer.writerows(pacer_info_list)
    print (f"Pacerinfo saved to: {pacer_file_path}")  
# GenAI generated code end

def process_folder(folder_path, params_file_path, waves_file_path, logger=None):
    """
    Processes all .drc files in the specified folder.
    """
    # Suppress FutureWarning
    pd.options.mode.chained_assignment = None  # default='warn'
    
    params_df = read_params_file(params_file_path)
    waves_df = read_waves_file(waves_file_path)
    for root, dirs, files in os.walk(folder_path):
        for file_name in files:
            if file_name.endswith(".drc"):
                if file_name.startswith(FILENAME):
                    data_file_path = os.path.join(root, file_name)
                    print(f"Processing {data_file_path}...")
                    
                    if logger:
                        logger.set_filename(data_file_path)  # Set the filename
    
                    trend_dataframe, wave_dataframe, freq, pacer_info_list = process_drc_file(data_file_path, params_df, waves_df, logger)
                    output_file_path = data_file_path.replace('.drc', '_trends.csv')
                    if logger:
                        logger.log_variables({"TrendRows":  len(trend_dataframe)})
                    save_dataframe_to_csv(trend_dataframe, output_file_path, logger)
                    
                    if freq > 0:
                        waves_output_file_path = data_file_path.replace('.drc', '_waves.csv')
                        if logger:
                            logger.log_variables({"WavesRows":  len(wave_dataframe)})
                        save_dataframe_to_csv(wave_dataframe, waves_output_file_path, logger)
                        mit_output_file_path = data_file_path.replace('.drc', '.dat')
                        
                        save_dataframe_to_mit(wave_dataframe, mit_output_file_path, freq)
                    
                    # GenAI generated code start
                    # Save pacer information to a CSV file if it contains more than one row
                    if len(pacer_info_list) > 1:
                        save_pacers_to_csv(pacer_info_list, data_file_path)
                    # GenAI generated code end
        
if __name__ == "__main__":
    logger = VariableLogger()
    parser = argparse.ArgumentParser(description="Process .drc files in a specified folder.")
    parser.add_argument("folder_path", nargs='?', default=os.getcwd(),
                        help="Path to the folder containing .drc files. Defaults to the current working directory.")
    parser.add_argument("params_file_path", nargs='?', default="params5_2.txt",
                        help="Path to the parameter configuration file. Defaults to 'params5_2.txt' in the current working directory.")
    parser.add_argument("waves_file_path", nargs='?', default="waves5_2.txt",
                        help="Path to the waveforms configuration file. Defaults to 'waves5_2.txt' in the current working directory.")
    args = parser.parse_args()

    process_folder(args.folder_path, args.params_file_path, args.waves_file_path, logger)
    logger.close_file()