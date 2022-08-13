#!/usr/bin/env python3

import os
import psycopg

connection_string = os.environ.get("CONNECTION_STRING")
if connection_string is None:
    connection_string = "postgresql://postgres:password@localhost:5432/gatling"

with psycopg.connect(connection_string) as conn:
    with conn.cursor() as cur:
        # Create schema as described here:
        # https://docs.timescale.com/getting-started/latest/create-
        # hypertable/#create-regular-postgresql-tables-for-relational-data

        # Create table to save loadtest results.
        cur.execute(
            """
            CREATE TABLE loadtest_result (
                time TIMESTAMPTZ NOT NULL,
                simulation TEXT NOT NULL,
                action TEXT NOT NULL,
                min INT NOT NULL,
                q50 INT NOT NULL,
                q75 INT NOT NULL,
                q95 INT NOT NULL,
                q99 INT NOT NULL,
                max INT NOT NULL,
                mean INT NOT NULL,
                std INT NOT NULL,
                total INT NOT NULL,
                ok INT NOT NULL,
                ko INT NOT NULL,
                ko_percentage INT NOT NULL,
                req_per_sec INT NOT NULL,
                UNIQUE (time, simulation, action)
            )
            """
        )

        # Create hypertable based on the previously created table.
        cur.execute(
            """
            SELECT create_hypertable('loadtest_result', 'time')
            """
        )

        # Create an additional index for faster queries on the simulation, action and time column.
        cur.execute(
            """
            CREATE INDEX ix_simulation_action_time ON loadtest_result(simulation, action, time DESC)
            """
        )

        conn.commit()
