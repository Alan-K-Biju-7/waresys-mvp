@celery_app.task(name="app.tasks.process_invoice")
def process_invoice(bill_id: int, file_path: str) -> Dict[str, Any]:
    """
    Background parse & persist:
    1) Prefer the unified pipeline.
    2) Else use adapter path and attach vendor safely.
    """
