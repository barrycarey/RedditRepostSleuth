from typing import Dict

from redditrepostsleuth.core.db.databasemodels import MonitoredSub


def monitored_sub_from_dict(data: Dict) -> MonitoredSub:
    return MonitoredSub(
        id=data.get('id', None),
        active=data.get('active', None),
        repost_only=data.get('repost_only', None),
        report_submission=data.get('report_submission', None),
        report_msg=data.get('report_msg', None),
        target_hamming=data.get('target_hamming', None),
        target_annoy=data.get('target_annoy', None),
        target_days_old=data.get('target_days_old', None),
        same_sub_only=data.get('same_sub_only', None),
        notes=data.get('notes', None),
        sticky_comment=data.get('sticky_comment', None),
        repost_response_template=data.get('repost_response_template', None),
        oc_response_template=data.get('oc_response_template', None),
        search_depth=data.get('search_depth', None),
        meme_filter=data.get('meme_filter', None),
    )