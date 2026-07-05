import json
from pathlib import Path
import pymysql
import logging

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def get_aiven_secretes(secrets_path, key):
    

    try:
        # Open and load the JSON file
        with open(secrets_path, "r", encoding="utf-8") as file:
            secrets = json.load(file)
        
        # Access individual variables using dictionary keys
        # DATABASE_NAME = secrets["db"]
        # HOST = secrets["host"]
        # PASSWORD = secrets["password"]
        # USER = secrets["user"]
        value = secrets[key]
        print(key + " fetched") 

    except FileNotFoundError:
        print(f"Error: The file {secrets_path} was not found.")
    except json.JSONDecodeError:
        print("Error: The file is not a valid JSON format.")
    except KeyError as e:
        print(f"Error: Missing the expected secret key: {e}")

    return value

#Function used to test aiven connection during the scrip writing process
def establish_connection(database, host, password, user):

    log.info(f"Attemptign aiven connection at host: {host}, database: {database}")


    timeout = 10
    connection = pymysql.connect(
    charset="utf8mb4",
    connect_timeout=timeout,
    cursorclass=pymysql.cursors.DictCursor,
    database=database,
    host=host,
    password=password,
    read_timeout=timeout,
    port=15969,
    user=user,
    write_timeout=timeout,
    )
    
    try:
        cursor = connection.cursor()
        cursor.execute("CREATE TABLE mytest (id INTEGER PRIMARY KEY)")
        cursor.execute("INSERT INTO mytest (id) VALUES (1), (2)")
        cursor.execute("SELECT * FROM mytest")
        print(cursor.fetchall())
    finally:
        connection.close()


def load_csv_to_database(csv_path,database, host, password, user):
    log.info(f"Attemptign aiven connection at host: {host}, database: {database}")


    timeout = 10
    connection = pymysql.connect(
    charset="utf8mb4",
    connect_timeout=timeout,
    cursorclass=pymysql.cursors.DictCursor,
    db=database,
    host=host,
    password=password,
    read_timeout=timeout,
    port=15969,
    user=user,
    write_timeout=timeout,
    )

def main():
    # Get the aiven connection variables
    secrets_path = Path("secrets/avian_creds.json")
    database = get_aiven_secretes(secrets_path=secrets_path, key="db")
    host = get_aiven_secretes(secrets_path=secrets_path, key="host")
    password = get_aiven_secretes(secrets_path=secrets_path, key="password")
    user = get_aiven_secretes(secrets_path=secrets_path, key="user")
    
    #Establish connection
    establish_connection(database=database, host=host, password=password, user=user)

main()