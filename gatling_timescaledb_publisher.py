#!/usr/bin/env python3

import numpy as np
import os
import pandas as pd
import psycopg
import sys

# Configure display parameters to print all columns of the data frame
pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', 100)
pd.set_option('display.width', 1000)


def read_simulation_log_metadata(path):
    # Read the first line with the header of the simulation log file
    df = pd.read_csv(path, sep='\t', on_bad_lines='skip', nrows=1)

    # Check that it's a valid file by validating the first cell
    content_type = df.columns[0]
    assert content_type == 'RUN'

    # Extract parameters about the load test from the header
    simulation_class_name = df.columns[1]
    simulation_name = df.columns[2]
    run_start_date = pd.to_datetime(df.columns[3], unit='ms')
    gating_version = df.columns[5]

    return simulation_class_name, simulation_name, run_start_date, gating_version


def read_simulation_log_file(path):
    # Read the relevant 6 columns.
    #
    # Some information about the data format can be found here:
    # https://github.com/nuxeo/gatling-report/blob/master/src/main/java/org/nuxeo/tools/gatling/report/SimulationParserV35.java
    #
    # The simulation.log file looks like it contains information about the execution of:
    # - Scenarios (by user)
    #   * 2 Rows per execution, one for start-date, one for end-date
    #   * Columns are: type ('USER'), scenario_name, action ('START, 'END'), time, undefined, undefined, undefined
    # - Actions
    #   * 1 Row per request
    #   * Columns are: type ('REQUEST'), undefined, action_name, start_time, end_time, success ('OK')
    #
    # Column 7 is skipped as it only appears in scenario-rows and only contains the value 'NaN'.
    # It can be made visible by adding 'unknown' to the 'names' attribute and adding the value '6' to usecols.
    df = pd.read_csv(path, sep='\t', on_bad_lines='warn', low_memory=False, usecols=[0, 1, 2, 3, 4, 5],
                     names=['type', 'scenario', 'action', 'start', 'end', 'success', 'unknown'])

    # Optionally check data types of columns if necessary
    # print(df.dtypes)
    # print(df.head(10))

    # Remove elements of type 'USER' as they only contain scenario related data
    # like scenario start_time and end_time, but we aren't interested in them.
    #
    # Drop column 'type' as it will only contain the value 'REQUEST'.
    # Drop column 'scenario' as there's no request related information in this column.
    df = df[df['type'] == 'REQUEST'].drop('type', axis=1).drop('scenario', axis=1)

    # Rename columns to be request specific
    df.columns = ['action', 'start', 'end', 'success']

    # Add request duration column
    df['duration'] = pd.to_numeric(df['end']) - pd.to_numeric(df['start'])

    start_time = pd.to_numeric(df['start']).min().astype(int)
    end_time = pd.to_numeric(df['end']).max().astype(int)
    load_test_duration = (end_time - start_time) / 1000  # in seconds
    load_test_duration_as_int = np.rint(load_test_duration).astype(int)

    # Drop 'start' and 'end' column as they are no longer relevant for the aggregation
    df = df.drop('start', axis=1).drop('end', axis=1)

    # Count successful and failed requests per action
    df_success_count = df[df['success'] == 'OK'].drop('duration', axis=1).groupby(['action']).agg(['count'])
    df_failed_count = df[df['success'] != 'OK'].drop('duration', axis=1).groupby(['action']).agg(['count'])

    # Calculate aggregated metrics
    df_aggregated = df.drop('success', axis=1).groupby(['action']).agg(
        [
            'min',
            lambda x: np.ceil(x.quantile(.5)).astype(int),
            lambda x: np.ceil(x.quantile(.75)).astype(int),
            lambda x: np.ceil(x.quantile(.95)).astype(int),
            lambda x: np.ceil(x.quantile(.99)).astype(int),
            'max',
            lambda x: np.ceil(x.mean()).astype(int),
            lambda x: np.ceil(x.std()).astype(int),
            'count',
        ])

    # Add columns with successful / failure counts to the aggregation dataframe
    df_aggregated = df_aggregated.merge(df_success_count, on=['action'], how='left')
    df_aggregated = df_aggregated.merge(df_failed_count, on=['action'], how='left')

    # Rename columns
    df_aggregated.columns = ['min', 'q50', 'q75', 'q95', 'q99', 'max', 'mean', 'std',
                             'total', 'ok', 'ko']

    # Fill empty columns of request stats with the value 0
    df_aggregated['ok'] = df_aggregated['ok'].fillna(0).astype(int)
    df_aggregated['ko'] = df_aggregated['ko'].fillna(0).astype(int)

    # Add column with calculated percentage of failed requests
    df_aggregated['ko_percentage'] = np.rint(
        (df_aggregated['ko'].astype(float) / df_aggregated['total'].astype(float)) * 100).astype(int)

    # Add column with request-per-second metric
    df_aggregated['req_per_sec'] = (df_aggregated['total'].astype(float) / load_test_duration).round(3)

    return load_test_duration_as_int, df_aggregated


def read_simulation_log(file_name):
    # Read metadata
    simulation_class_name, simulation_name, run_start_date, gating_version = read_simulation_log_metadata(
        path=file_name)

    # Print metadata
    print('Simulation class name:', simulation_class_name)
    print('Simulation name:', simulation_name)
    print('Run start date:', run_start_date)
    print('Gatling version:', gating_version)

    # Read simulation log file
    load_test_duration, df = read_simulation_log_file(file_name)

    # Print parsed data from simulation log file
    print('Duration:', load_test_duration, 'seconds')
    print('Results:\n', df)

    return simulation_name, run_start_date, df


def write_to_timescale_db(simulation_name, run_start_date, df):
    # Check if connection string environment variable is set or set default value
    connection_string = os.environ.get("CONNECTION_STRING")
    if connection_string is None:
        connection_string = "postgresql://postgres:password@localhost:5432/gatling"

    # Connect to database and insert data from dataframe
    with psycopg.connect(connection_string) as conn:
        with conn.cursor() as cur:
            # Write each row of the dataframe into a database row
            for _, row in df.iterrows():
                cur.execute(
                    """
                    INSERT INTO loadtest_result(time,simulation,action,min, 
                        q50,q75,q95,q99,max,mean,std,total,ok,ko,ko_percentage,req_per_sec) 
                    VALUES ('%s', '%s', '%s',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """ % (
                        run_start_date,
                        simulation_name,
                        row.name,
                        row['min'].astype(int),
                        row['q50'].astype(int),
                        row['q75'].astype(int),
                        row['q95'].astype(int),
                        row['q99'].astype(int),
                        row['max'].astype(int),
                        row['mean'].astype(int),
                        row['std'].astype(int),
                        row['total'].astype(int),
                        row['ok'].astype(int),
                        row['ko'].astype(int),
                        row['ko_percentage'].astype(int),
                        row['req_per_sec'].astype(int)))


def main(args=None):
    # Check if a custom file name was provided as parameter or set simulation.log as default
    file_name = "simulation.log"
    if args is not None:
        if len(args) == 1:
            file_name = args[0]

    # Read metadata and parse the simulation log file
    simulation_name, run_start_date, df = read_simulation_log(file_name)

    # Write parsed data into the database
    write_to_timescale_db(simulation_name, run_start_date, df)


# Call main method with (optional) parameters
if __name__ == '__main__':
    args = None
    if sys.argv is not None:
        args = sys.argv[1:]
    sys.exit(main(args))
