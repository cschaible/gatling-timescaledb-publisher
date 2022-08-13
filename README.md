# Gatling Timescale DB Publisher

By default, Gatling generates HTML reports for each executed simulation. Individual reports though 
cannot be compared with previous runs easily. To simplify the comparison of multiple runs and to 
store results over a longer period of time easy accessible, this repository contains scripts to publish
results to a timescale db (PostgreSQL Plugin) to display them in Grafana.

## Scripts

- **migrate_db.py**  
  Python script to migrate the database schema to store loadtest results.  
  Set environment variable `CONNECTION_STRING` to connect to the correct database.  
  Default is: *postgresql://postgres:password@localhost:5432/gatling*  
  There's no console output if everything finished successfully.
- **gatling_timescaledb_publisher.py**  
  Python script to publish raw data of a `simulation.log` file to the timescale db.  
  Set environment variable `CONNECTION_STRING` to connect to the correct database.  
  Default is: *postgresql://postgres:password@localhost:5432/gatling*  
  Optional script parameter: <simulation.log file name>
- **docker/docker-compose.yml**  
  Docker compose yaml file to start a local timescale db, grafana and pgAdmin.
  Two dashboards are automatically provisioned to grafana.  
  Login credentials:
  - Grafana (port 3000):
    - username: admin
    - password: secret
  - pgAdmin (port 5433):
    - UI
      - pgAdmin-username: test@example.com
      - pgAdmin-password: secret
    - Server-Connection
      - hostname: timescaledb
      - username: postgres
      - password: password

## Run locally

The docker-compose.yml file can be started by executing: `docker-compose up -d`

Install required python dependencies: `pip install -r requirements.txt`

Initialize the timescale db by running: `./migrate_db.py`.

Place the `simulation.log` file into the directory where the two python scripts are located.

Run the publisher script `./gatling_timescaledb_publisher.py`.
The script parses the `simulation.log` file, prints the parsed data, and saves it
in the timescale db.

Open a browser and navigate to [http://localhost:3000](http://localhost:3000). Login with the 
grafana credentials as described above.

The docker containers can be stopped and removed by running: `docker-compose down`

## Run remotely

Set `CONNECTION_STRING` environment variable with a valid postgresql connection string
for the timescale db.

Execute the scripts as described above.

## Python versions
The script was developed and tested with Python 3.8.

## License
The code in this repository is licensed under the [MIT License](LICENSE-MIT).
The used libraries under their respective licenses (see [requirements.txt](requirements.txt)).