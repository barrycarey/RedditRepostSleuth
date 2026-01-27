from datetime import datetime
from typing import List, Optional

from redditrepostsleuth.core.db.databasemodels import SpamTrainingLabels


class SpamTrainingLabelsRepo:

    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item: SpamTrainingLabels):
        self.db_session.add(item)

    def get_by_id(self, id: int) -> Optional[SpamTrainingLabels]:
        return self.db_session.query(SpamTrainingLabels).filter(
            SpamTrainingLabels.id == id
        ).first()

    def get_by_username(self, username: str) -> List[SpamTrainingLabels]:
        """Get all labels for a username (may have multiple over time)."""
        return self.db_session.query(SpamTrainingLabels).filter(
            SpamTrainingLabels.username == username
        ).order_by(SpamTrainingLabels.labeled_at.desc()).all()

    def get_latest_by_username(self, username: str) -> Optional[SpamTrainingLabels]:
        """Get the most recent label for a username."""
        return self.db_session.query(SpamTrainingLabels).filter(
            SpamTrainingLabels.username == username
        ).order_by(SpamTrainingLabels.labeled_at.desc()).first()

    def get_all(self, limit: int = None) -> List[SpamTrainingLabels]:
        query = self.db_session.query(SpamTrainingLabels)
        if limit:
            query = query.limit(limit)
        return query.all()

    def get_by_label(self, label: str, limit: int = None) -> List[SpamTrainingLabels]:
        query = self.db_session.query(SpamTrainingLabels).filter(
            SpamTrainingLabels.label == label
        ).order_by(SpamTrainingLabels.labeled_at.desc())
        if limit:
            query = query.limit(limit)
        return query.all()

    def get_by_source(self, label_source: str, limit: int = None) -> List[SpamTrainingLabels]:
        query = self.db_session.query(SpamTrainingLabels).filter(
            SpamTrainingLabels.label_source == label_source
        ).order_by(SpamTrainingLabels.labeled_at.desc())
        if limit:
            query = query.limit(limit)
        return query.all()

    def get_training_data(self, label: str = None, since: datetime = None, limit: int = None) -> List[SpamTrainingLabels]:
        """Get training data, optionally filtered by label and date."""
        query = self.db_session.query(SpamTrainingLabels)
        if label:
            query = query.filter(SpamTrainingLabels.label == label)
        if since:
            query = query.filter(SpamTrainingLabels.labeled_at >= since)
        query = query.order_by(SpamTrainingLabels.labeled_at.desc())
        if limit:
            query = query.limit(limit)
        return query.all()

    def count_by_label(self) -> dict:
        """Get counts of labels by type."""
        from sqlalchemy import func
        results = self.db_session.query(
            SpamTrainingLabels.label,
            func.count(SpamTrainingLabels.id).label('count')
        ).group_by(SpamTrainingLabels.label).all()
        return {row.label: row.count for row in results}

    def delete_by_id(self, id: int) -> bool:
        """Delete a label record. Returns True if deleted."""
        result = self.db_session.query(SpamTrainingLabels).filter(
            SpamTrainingLabels.id == id
        ).delete(synchronize_session=False)
        return result > 0
