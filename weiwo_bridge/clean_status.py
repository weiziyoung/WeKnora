from database import get_session, DocumentStatus
from sqlalchemy import or_

def clean_status():
    session = get_session()
    try:
        # Query for records that match the criteria
        # "Status  409:" (two spaces)
        # "Status 413:" (one space)
        records = session.query(DocumentStatus).filter(
            or_(
                DocumentStatus.failed_msg.like("Status 409:%"),
                DocumentStatus.failed_msg.like("Status 413:%")
            )
        ).all()

        print(f"Found {len(records)} records potentially matching criteria.")

        count_409 = 0
        count_413 = 0

        for record in records:
            original_msg = record.failed_msg
            if original_msg.startswith("Status 409:"):
                record.failed_msg = "Status 409"
                count_409 += 1
            elif original_msg.startswith("Status 413:"):
                record.failed_msg = "Status 413"
                count_413 += 1
        
        session.commit()
        print(f"Successfully updated {count_409} records for 'Status 409'")
        print(f"Successfully updated {count_413} records for 'Status 413'")
        
    except Exception as e:
        session.rollback()
        print(f"Error occurred: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    clean_status()
