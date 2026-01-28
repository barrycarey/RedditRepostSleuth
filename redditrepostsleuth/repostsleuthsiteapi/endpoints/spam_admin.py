"""
Spam Admin Endpoints - Phase 4: Admin API for Spam Detection

Provides administrative endpoints for managing and monitoring the
spam detection system.
"""
import html
import json
import logging
from datetime import datetime
from typing import Optional

from falcon import Request, Response, HTTPBadRequest, HTTPNotFound, HTTPForbidden

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import SpamTrainingLabels
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.util.reddithelpers import get_user_data
from redditrepostsleuth.repostsleuthsiteapi.util.helpers import get_token_from_header, is_site_admin

log = logging.getLogger(__name__)


def _require_admin_auth(req: Request, uowm: UnitOfWorkManager) -> dict:
    """Verify the request is from an authenticated site admin."""
    token = get_token_from_header(req)
    user_data = get_user_data(token)
    if not user_data:
        raise HTTPForbidden(title='Authentication Failed',
                           description='Could not verify your Reddit identity')
    if not is_site_admin(user_data, uowm):
        raise HTTPForbidden(title='Access Denied',
                           description='You must be a site administrator')
    return user_data


class SpamScoreUserEndpoint:
    """POST /api/admin/spam/score - Trigger spam scoring for a user."""

    def __init__(self, uowm: UnitOfWorkManager, config: Config):
        self.uowm = uowm
        self.config = config

    def on_post(self, req: Request, resp: Response):
        """
        Trigger spam scoring for a specific user.

        Request body:
            {
                "username": "string",
                "force": bool (optional, default false)
            }

        Response:
            {
                "status": "queued" | "skipped",
                "username": "string",
                "message": "string"
            }
        """
        _require_admin_auth(req, self.uowm)

        try:
            body = json.load(req.bounded_stream)
        except json.JSONDecodeError:
            raise HTTPBadRequest(
                title='Invalid JSON',
                description='Request body must be valid JSON'
            )

        username = body.get('username')
        force = body.get('force', False)

        if not username:
            raise HTTPBadRequest(
                title='Missing Username',
                description='Username is required'
            )

        # Check if user was recently analyzed (unless forcing)
        if not force:
            with self.uowm.start() as uow:
                if uow.spam_features.user_was_recently_analyzed(username, within_days=1):
                    resp.text = json.dumps({
                        'status': 'skipped',
                        'username': username,
                        'message': 'User was recently analyzed. Use force=true to override.'
                    })
                    return

        # Queue the scoring task
        try:
            from redditrepostsleuth.core.celery.tasks.spam_detection_tasks import score_and_flag_user
            score_and_flag_user.delay(username, update_user_review=True)

            resp.text = json.dumps({
                'status': 'queued',
                'username': username,
                'message': f'Spam scoring task queued for {username}'
            })
            log.info('Admin triggered spam scoring for user: %s (force=%s)', username, force)
        except Exception as e:
            log.error('Failed to queue spam scoring for %s: %s', username, str(e))
            raise HTTPBadRequest(
                title='Task Queue Error',
                description=f'Failed to queue scoring task: {str(e)}'
            )


class SpamUserDetailsEndpoint:
    """GET /api/admin/spam/user/{username} - Get spam details for a user."""

    def __init__(self, uowm: UnitOfWorkManager, config: Config):
        self.uowm = uowm
        self.config = config

    def on_get(self, req: Request, resp: Response, username: str):
        """
        Get detailed spam information for a user.

        Response:
            {
                "username": "string",
                "spam_features": {...} | null,
                "user_review": {...} | null,
                "training_labels": [...],
                "activity_stats": {...}
            }
        """
        _require_admin_auth(req, self.uowm)

        with self.uowm.start() as uow:
            # Get spam features
            features = uow.spam_features.get_by_username(username)
            features_dict = features.to_dict() if features else None

            # Get user review
            review = uow.user_review.get_by_username(username)
            review_dict = None
            if review:
                review_dict = {
                    'username': review.username,
                    'spam_score': review.spam_score,
                    'spam_score_confidence': review.spam_score_confidence,
                    'spam_score_updated_at': review.spam_score_updated_at.isoformat() if review.spam_score_updated_at else None,
                    'risk_level': review.risk_level,
                    'content_links_found': review.content_links_found,
                    'notes': review.notes,
                }

            # Get training labels
            labels = uow.spam_training_labels.get_by_username(username)
            labels_list = [
                {
                    'id': l.id,
                    'label': l.label,
                    'confidence': l.confidence,
                    'label_source': l.label_source,
                    'labeled_by': l.labeled_by,
                    'labeled_at': l.labeled_at.isoformat() if l.labeled_at else None,
                    'notes': l.notes,
                }
                for l in labels
            ]

            # Get activity stats
            activity_stats = uow.author_activity.get_author_stats(username)

        resp.text = json.dumps({
            'username': username,
            'spam_features': features_dict,
            'user_review': review_dict,
            'training_labels': labels_list,
            'activity_stats': activity_stats,
        })


class SpamHighRiskUsersEndpoint:
    """GET /api/admin/spam/high-risk - List high-risk users."""

    def __init__(self, uowm: UnitOfWorkManager, config: Config):
        self.uowm = uowm
        self.config = config

    def on_get(self, req: Request, resp: Response):
        """
        Get list of high-risk users.

        Query params:
            - min_score: float (default 0.6)
            - limit: int (default 50, max 200)

        Response:
            {
                "users": [
                    {
                        "username": "string",
                        "spam_score": float,
                        "risk_level": "string",
                        "computed_at": "string",
                        ...
                    }
                ],
                "total": int
            }
        """
        _require_admin_auth(req, self.uowm)

        min_score = req.get_param_as_float('min_score') or 0.6
        limit = req.get_param_as_int('limit') or 50
        limit = min(limit, 200)

        with self.uowm.start() as uow:
            high_risk = uow.spam_features.get_high_spam_scores(
                threshold=min_score,
                limit=limit
            )

            users = []
            for f in high_risk:
                users.append({
                    'username': f.username,
                    'spam_score': f.spam_score,
                    'spam_score_confidence': f.spam_score_confidence,
                    'repost_ratio': f.repost_ratio,
                    'total_posts_indexed': f.total_posts_indexed,
                    'total_reposts_detected': f.total_reposts_detected,
                    'account_age_days': f.account_age_days,
                    'account_suspended': f.account_suspended,
                    'computed_at': f.computed_at.isoformat() if f.computed_at else None,
                    'tier2_enriched_at': f.tier2_enriched_at.isoformat() if f.tier2_enriched_at else None,
                })

        resp.text = json.dumps({
            'users': users,
            'total': len(users),
            'min_score': min_score,
            'limit': limit,
        })


class SpamLabelUserEndpoint:
    """POST /api/admin/spam/label - Manually label a user."""

    def __init__(self, uowm: UnitOfWorkManager, config: Config):
        self.uowm = uowm
        self.config = config

    def on_post(self, req: Request, resp: Response):
        """
        Manually label a user for training data.

        Request body:
            {
                "username": "string",
                "label": "SPAM" | "LEGITIMATE" | "UNKNOWN",
                "confidence": float (0.0-1.0),
                "notes": "string" (optional)
            }

        Response:
            {
                "status": "created",
                "label_id": int,
                "username": "string",
                "label": "string"
            }
        """
        user_data = _require_admin_auth(req, self.uowm)

        try:
            body = json.load(req.bounded_stream)
        except json.JSONDecodeError:
            raise HTTPBadRequest(
                title='Invalid JSON',
                description='Request body must be valid JSON'
            )

        username = body.get('username')
        label = body.get('label')
        confidence = body.get('confidence', 1.0)
        labeled_by = user_data['name']
        notes = body.get('notes', '')

        # Validate required fields
        if not username:
            raise HTTPBadRequest(
                title='Missing Username',
                description='Username is required'
            )

        valid_labels = ['SPAM', 'LEGITIMATE', 'UNKNOWN']
        if label not in valid_labels:
            raise HTTPBadRequest(
                title='Invalid Label',
                description=f'Label must be one of: {", ".join(valid_labels)}'
            )

        if not 0.0 <= confidence <= 1.0:
            raise HTTPBadRequest(
                title='Invalid Confidence',
                description='Confidence must be between 0.0 and 1.0'
            )

        with self.uowm.start() as uow:
            # Get current spam features for snapshot
            features = uow.spam_features.get_by_username(username)
            feature_snapshot = features.to_dict() if features else {}

            # Create training label
            training_label = SpamTrainingLabels(
                username=username,
                label=label,
                confidence=confidence,
                label_source='admin_manual',
                labeled_by=labeled_by,
                notes=html.escape(notes[:500]) if notes else None,
                feature_snapshot=feature_snapshot,
            )
            uow.spam_training_labels.add(training_label)
            uow.commit()

            label_id = training_label.id

        log.info(
            'Admin created training label: user=%s, label=%s, confidence=%.2f, by=%s',
            username, label, confidence, labeled_by
        )

        resp.text = json.dumps({
            'status': 'created',
            'label_id': label_id,
            'username': username,
            'label': label,
        })


class SpamStatsEndpoint:
    """GET /api/admin/spam/stats - Get spam detection statistics."""

    def __init__(self, uowm: UnitOfWorkManager, config: Config):
        self.uowm = uowm
        self.config = config

    def on_get(self, req: Request, resp: Response):
        """
        Get overall spam detection statistics.

        Response:
            {
                "total_users_analyzed": int,
                "high_risk_users": int,
                "suspended_users": int,
                "label_counts": {...},
                "score_distribution": {...}
            }
        """
        _require_admin_auth(req, self.uowm)

        with self.uowm.start() as uow:
            # Get total users analyzed
            all_features = uow.spam_features.get_all()
            total_analyzed = len(all_features)

            # Count by risk level
            high_risk = sum(1 for f in all_features if f.spam_score and f.spam_score >= 0.6)
            critical_risk = sum(1 for f in all_features if f.spam_score and f.spam_score >= 0.8)

            # Get suspended users
            suspended = uow.spam_features.get_suspended_users(limit=1000)
            suspended_count = len(suspended)

            # Get label distribution
            label_counts = uow.spam_training_labels.count_by_label()

            # Calculate score distribution
            score_distribution = {
                'low': 0,      # < 0.3
                'medium': 0,   # 0.3 - 0.6
                'high': 0,     # 0.6 - 0.8
                'critical': 0  # >= 0.8
            }
            for f in all_features:
                if f.spam_score is None:
                    continue
                if f.spam_score < 0.3:
                    score_distribution['low'] += 1
                elif f.spam_score < 0.6:
                    score_distribution['medium'] += 1
                elif f.spam_score < 0.8:
                    score_distribution['high'] += 1
                else:
                    score_distribution['critical'] += 1

        resp.text = json.dumps({
            'total_users_analyzed': total_analyzed,
            'high_risk_users': high_risk,
            'critical_risk_users': critical_risk,
            'suspended_users': suspended_count,
            'label_counts': label_counts,
            'score_distribution': score_distribution,
        })


def register_spam_admin_endpoints(api, uowm: UnitOfWorkManager, config: Config):
    """
    Register all spam admin endpoints with the Falcon API.

    Args:
        api: Falcon API instance
        uowm: UnitOfWorkManager for database access
        config: Application configuration
    """
    # POST /api/admin/spam/score - Trigger scoring for a user
    api.add_route('/api/admin/spam/score', SpamScoreUserEndpoint(uowm, config))

    # GET /api/admin/spam/user/{username} - Get user details
    api.add_route('/api/admin/spam/user/{username}', SpamUserDetailsEndpoint(uowm, config))

    # GET /api/admin/spam/high-risk - List high-risk users
    api.add_route('/api/admin/spam/high-risk', SpamHighRiskUsersEndpoint(uowm, config))

    # POST /api/admin/spam/label - Create training label
    api.add_route('/api/admin/spam/label', SpamLabelUserEndpoint(uowm, config))

    # GET /api/admin/spam/stats - Get statistics
    api.add_route('/api/admin/spam/stats', SpamStatsEndpoint(uowm, config))

    log.info('Registered spam admin endpoints')
