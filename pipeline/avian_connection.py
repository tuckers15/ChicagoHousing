import json
from pathlib import Path
import pandas as pd
import logging
import sqlalchemy as sa
from urllib.parse import quote
from sqlalchemy import Integer
from sqlalchemy.dialects.mysql import INTEGER
# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

#----------------------------------------------------------------
# Constants 
#----------------------------------------------------------------
SECRETS_PATH = Path("secrets/avian_creds.json")

TARGET_TABLE = "parcel_sales_staging"

DROP_TABLE_SQL = f"""
DROP TABLE IF EXISTS {TARGET_TABLE};
"""

CREATE_TABLE_SQL = f"""

CREATE TABLE IF NOT EXISTS {TARGET_TABLE} (
    id                              INT AUTO_INCREMENT PRIMARY KEY,
 
    -- Parcel identifier
    pin                             VARCHAR(14)      NOT NULL,
 
    -- Sale details
    year                            SMALLINT,
    township_code                   TINYINT,
    nbhd                            VARCHAR(20),
    property_class                  VARCHAR(10),
    class_category                  VARCHAR(50),
    sale_date                       DATE,
    standard_sale_date              DATE,
    is_mydec_date                   TINYINT(1),
    sale_price                      DECIMAL(12, 2),
    sale_type                       VARCHAR(50),
 
    -- Document / deed info
    doc_no                          VARCHAR(50),
    deed_type                       VARCHAR(10),
    mydec_deed_type                 VARCHAR(100),
 
    -- Multi-sale info
    is_multisale                    TINYINT(1),
    num_parcels_sale                SMALLINT,
 
    -- Audit filter flags (retained for reference)
    sale_filter_same_sale_within_365  TINYINT(1),
    sale_filter_less_than_10k         TINYINT(1),
    sale_filter_deed_type             TINYINT(1),
 
    -- Geocoding & neighborhood
    lat                             DECIMAL(9, 6),
    lon                             DECIMAL(9, 6),
    chicago_community_area_name     VARCHAR(100),
 
    -- Row provenance
    row_id                          VARCHAR(50),
 
    -- Indexes for common query patterns
    INDEX idx_pin                   (pin),
    INDEX idx_year                  (year),
    INDEX idx_sale_date             (sale_date),
    INDEX idx_community_area        (chicago_community_area_name),
    INDEX idx_class_category        (class_category),
    INDEX idx_township              (township_code)
)
"""
DROP_COLUMNS = ["seller_name", "buyer_name"]

#------------------------------------------------------
# Helper functions
#------------------------------------------------------

def create_table(engine, target_table):
    with engine.connect() as conn:
        log.info(f"Dropping table '{target_table}' if it exist...")
        conn.execute(sa.text(DROP_TABLE_SQL))
        log.info(f"Creating table '{target_table}'")
        conn.execute(sa.text(CREATE_TABLE_SQL))
        conn.commit()
    log.info("Table ready.")
 

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
def establish_connection(database, host, password, user, port=15969):

    log.info(f"Attempting aiven connection at host: {host}, database: {database}")

    encoded_user = quote(user, safe='')
    encoded_password = quote(password, safe='')
    
    engine = sa.create_engine(
        f"mysql+pymysql://{encoded_user}:{encoded_password}@{host}:{port}/{database}"
    )

    return engine

def test_engine(sql_engine):
    engine = sql_engine

    metadata = sa.MetaData()

    # reflect=True tells SQLAlchemy to query the DB for the table's column definitions
    mytest = sa.Table("mytest", metadata, autoload_with=engine)

    stmt = sa.select(mytest)  # equivalent to SELECT * FROM mytest

    with engine.connect() as connection:
        results = connection.execute(stmt).all()
        print (results)
    


# Abandoned the below function due to errors related to indexing. Go forward solution is to hardcode and create the target
# table, along with its indexes, before loading the dataframe to aiven.
# TODO: come back and clean up code after refactoring functions for these changes. 

# def load_csv_to_database(csv_path, sql_engine, target_table):
#     #Using a whitelist system to discourage sql injections
#     ALLOWED_TABLES = ["parcel_sales_staging"] #Update this before attempting to load to other tables

#     if target_table not in ALLOWED_TABLES:
#         raise ValueError(f"Invalid table name: {target_table}")

#     log.info(f"Attempting to load {csv_path} to Aiven DB at {target_table}")

#     engine = sql_engine

#     df = pd.read_csv(csv_path)
#     print(len(df.index))
#     df = df.reset_index(drop=True)  # ensures clean 0-based integer index
#     print(f"DF Index: {df.index}") # should show RangeIndex(start=0, stop=N, step=1)
    
#     df.to_sql(
#         name=target_table,
#         con=engine,
#         if_exists="replace", #TODO: come back and modify this when there is a go forward data refresh plan
#         index=True,
#         index_label="id",
#         chunksize=1000,
#         dtype={'id': 'INTEGER PRIMARY KEY AUTOINCREMENT'}
#         #dtype={"id": INTEGER(unsigned=True)}
#     )
#     log.info(f"Successfully loaded csv to {target_table}.")

#     with engine.connect() as conn:
#         result = conn.execute(sa.text(f"SELECT * FROM {target_table} LIMIT 5"))
#         print(result)

#----------------------------------------
# Getting the clean DF
#----------------------------------------
def load_csv(path: str) -> pd.DataFrame:
    log.info(f"Reading CSV: {path}")
    df = pd.read_csv(path)
    log.info(f"  Raw shape: {df.shape[0]:,} rows × {df.shape[1]} columns")
 
    # Drop the unnamed index column pandas adds on CSV export
    if df.columns[0] in ("", "Unnamed: 0"):
        df = df.drop(columns=df.columns[0])
 
    # Drop columns not going into the database
    df = df.drop(columns=[c for c in DROP_COLUMNS if c in df.columns])
    log.info(f"  Dropped columns: {DROP_COLUMNS}")
 
    # Ensure PINs are zero-padded 
    df["pin"] = df["pin"].astype(str).str.zfill(14)
 
    # Cast boolean flag columns to int (MySQL TINYINT(1))
    bool_cols = [
        "is_mydec_date",
        "is_multisale",
        "sale_filter_same_sale_within_365",
        "sale_filter_less_than_10k",
        "sale_filter_deed_type",
    ]
    for col in bool_cols:
        if col in df.columns:
            df[col] = df[col].map(
                {True: 1, False: 0, "True": 1, "False": 0, 1: 1, 0: 0}
            ).astype("Int8")  # nullable integer — handles NaN without crashing
 
    # Cast numeric columns
    df["sale_price"]      = pd.to_numeric(df["sale_price"],      errors="coerce")
    df["lat"]             = pd.to_numeric(df["lat"],             errors="coerce")
    df["lon"]             = pd.to_numeric(df["lon"],             errors="coerce")
    df["year"]            = pd.to_numeric(df["year"],            errors="coerce").astype("Int16")
    df["township_code"]   = pd.to_numeric(df["township_code"],   errors="coerce").astype("Int8")
    df["num_parcels_sale"]= pd.to_numeric(df["num_parcels_sale"],errors="coerce").astype("Int16")
 
    log.info(f"  Final shape: {df.shape[0]:,} rows × {df.shape[1]} columns")
    log.info(f"  Columns to insert: {list(df.columns)}")
    return df

#------------------------------------
# Loading the DF to MySql DB on Aiven
#------------------------------------

def insert_data(df: pd.DataFrame, engine):
    log.info(f"Inserting {len(df):,} rows into '{TARGET_TABLE}'...")
    df.to_sql(
        name=TARGET_TABLE,
        con=engine,
        if_exists="append",   # TODO: come back and modify/verify this when there is a go forward data refresh plan
        index=False,          # id is AUTO_INCREMENT in the table, don't write df index
        chunksize=1000,
    )
    log.info("Insert complete.")

def verify_load(engine):
    with engine.connect() as conn:
        result = conn.execute(sa.text(f"SELECT * FROM {TARGET_TABLE} LIMIT 5"))
        for row in result:
            log.info(f" {row}")

def main():
    # Get the aiven connection variables
    secrets_path = Path("secrets/avian_creds.json")
    database = get_aiven_secretes(secrets_path=SECRETS_PATH, key="db")
    host = get_aiven_secretes(secrets_path=SECRETS_PATH, key="host")
    password = get_aiven_secretes(secrets_path=SECRETS_PATH, key="password")
    user = get_aiven_secretes(secrets_path=SECRETS_PATH, key="user")
    
    #Establish connection
    engine = establish_connection(database=database, host=host, password=password, user=user)
    create_table(engine, TARGET_TABLE)

    df = load_csv(path="data/joined_parcel_data.csv")
    insert_data(df, engine)
    verify_load(engine)
    

main()