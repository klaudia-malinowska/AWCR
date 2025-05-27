
from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, udf, window
from pyspark.sql.types import StructType, StringType, IntegerType, TimestampType
import json
from datetime import datetime

# Inicjalizacja sesji Spark
spark = SparkSession.builder     .appName("FraudDetectionStreaming")     .getOrCreate()

spark.sparkContext.setLogLevel("WARN")

# Schemat danych transakcji
schema = StructType()     .add("user_id", IntegerType())     .add("amount", IntegerType())     .add("country", StringType())     .add("timestamp", StringType())  # zostanie sparsowany później

# Czytanie strumienia z Kafka
df_raw = spark.readStream     .format("kafka")     .option("kafka.bootstrap.servers", "kafka:9092")     .option("subscribe", "transactions")     .option("startingOffsets", "earliest")     .load()

df_json = df_raw.selectExpr("CAST(value AS STRING) as json_string")

df = df_json.select(from_json(col("json_string"), schema).alias("data")).select("data.*")

# Parsowanie timestamp
df = df.withColumn("timestamp", col("timestamp").cast(TimestampType()))

# UDF do obliczania punktów ryzyka
def calculate_score(amount, country, timestamp_str):
    score = 0
    if country and country != "PL":
        score += 2
    if amount and amount > 5000:
        score += 2
    if timestamp_str:
        try:
            hour = timestamp_str.hour
            if 0 <= hour < 5:
                score += 1
        except:
            pass
    return score

@udf(IntegerType())
def score_udf(amount, country, timestamp):
    return calculate_score(amount, country, timestamp)

df_scored = df.withColumn("score", score_udf(col("amount"), col("country"), col("timestamp")))

# Kategoryzacja ryzyka
@udf(StringType())
def risk_category(score):
    if score <= 2:
        return "normal"
    elif score <= 4:
        return "suspicious"
    else:
        return "fraud"

df_final = df_scored.withColumn("risk_level", risk_category(col("score")))

# Wypisywanie wyniku na konsolę
df_final.writeStream \
    .format("console") \
    .outputMode("append") \
    .option("truncate", False) \
    .start() \
    .awaitTermination()
