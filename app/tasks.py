    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("[task] DB error")
    except Exception as e:
        db.rollback()
        logger.exception("[task] unexpected failure")
    finally:
        db.close()
