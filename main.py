from ingestion.pipeline import Pipeline

if __name__ == "__main__":
    # Wrapper to run the ingestion pipeline
    pipeline = Pipeline()
    pipeline.run()
