"""Service for fetching Reddit subreddit traffic statistics using moderator OAuth tokens."""

import base64
import json as json_module
import logging
import zlib
from datetime import datetime
from typing import Dict, List, Optional, Text

import requests

log = logging.getLogger(__name__)


def get_subreddit_traffic(
    token: str,
    subreddit: str,
    user_agent: Text = 'windows.repostsleuthbot:v0.0.1 (by /u/barrycarey)'
) -> Optional[Dict]:
    """
    Fetch subreddit traffic statistics using a moderator's OAuth token.

    Reddit's traffic endpoint returns:
    - day: [[timestamp, unique_views, total_views, subscribers], ...]
    - hour: [[timestamp, unique_views, total_views], ...]
    - month: [[timestamp, unique_views, total_views, subscribers], ...]

    Args:
        token: Reddit OAuth access token (must belong to a moderator)
        subreddit: Name of the subreddit
        user_agent: User agent string for the request

    Returns:
        Dictionary with processed traffic data or None if request fails
    """
    headers = {'Authorization': f'Bearer {token}', 'User-Agent': user_agent}
    url = f'https://oauth.reddit.com/r/{subreddit}/about/traffic'

    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 404:
            log.warning('Traffic stats not available for %s (may be private or user is not a mod)', subreddit)
            return None
        if response.status_code != 200:
            log.error('Failed to get traffic for %s: status %s, response: %s',
                      subreddit, response.status_code, response.text)
            return None

        data = response.json()
        return _process_traffic_data(data)

    except requests.RequestException as e:
        log.error('Request error getting traffic for %s: %s', subreddit, e)
        return None
    except Exception as e:
        log.exception('Unexpected error getting traffic for %s', subreddit, exc_info=True)
        return None


def get_subreddit_traffic_praw(reddit, subreddit: str) -> Optional[Dict]:
    """
    Fetch subreddit traffic statistics using a PRAW Reddit instance.

    This uses the bot's credentials which have proper access to mod endpoints.

    Args:
        reddit: Authenticated PRAW Reddit instance
        subreddit: Name of the subreddit

    Returns:
        Dictionary with processed traffic data or None if request fails
    """
    try:
        sub = reddit.subreddit(subreddit)
        raw_data = sub.traffic()
        return _process_traffic_data(raw_data)
    except Exception as e:
        log.error('Failed to get traffic for %s via PRAW: %s', subreddit, e)
        return None


def _process_traffic_data(raw_data: Dict) -> Dict:
    """
    Process raw Reddit traffic data into a more usable format.

    Args:
        raw_data: Raw response from Reddit's traffic endpoint

    Returns:
        Processed traffic data with daily, hourly, and monthly breakdowns
    """
    result = {
        'daily': [],
        'hourly': [],
        'monthly': []
    }

    # Process daily data: [timestamp, unique, total, subscribers]
    if 'day' in raw_data:
        for entry in raw_data['day']:
            if len(entry) >= 4:
                result['daily'].append({
                    'date': datetime.fromtimestamp(entry[0]).strftime('%Y-%m-%d'),
                    'timestamp': entry[0],
                    'unique_views': entry[1],
                    'total_views': entry[2],
                    'subscribers': entry[3]
                })

    # Process hourly data: [timestamp, unique, total]
    # Aggregate by hour of day for average activity pattern
    if 'hour' in raw_data:
        hourly_totals = {}
        hourly_counts = {}

        for entry in raw_data['hour']:
            if len(entry) >= 3:
                hour = datetime.fromtimestamp(entry[0]).hour
                if hour not in hourly_totals:
                    hourly_totals[hour] = {'unique': 0, 'total': 0}
                    hourly_counts[hour] = 0

                hourly_totals[hour]['unique'] += entry[1]
                hourly_totals[hour]['total'] += entry[2]
                hourly_counts[hour] += 1

        # Calculate averages
        for hour in range(24):
            if hour in hourly_totals and hourly_counts[hour] > 0:
                result['hourly'].append({
                    'hour': hour,
                    'avg_unique_views': round(hourly_totals[hour]['unique'] / hourly_counts[hour]),
                    'avg_total_views': round(hourly_totals[hour]['total'] / hourly_counts[hour])
                })
            else:
                result['hourly'].append({
                    'hour': hour,
                    'avg_unique_views': 0,
                    'avg_total_views': 0
                })

    # Process monthly data: [timestamp, unique, total, subscribers]
    if 'month' in raw_data:
        for entry in raw_data['month']:
            if len(entry) >= 4:
                result['monthly'].append({
                    'month': datetime.fromtimestamp(entry[0]).strftime('%Y-%m'),
                    'timestamp': entry[0],
                    'unique_views': entry[1],
                    'total_views': entry[2],
                    'subscribers': entry[3]
                })

    return result


def debug_oauth_token(
    token: str,
    subreddit: str,
    user_agent: Text = 'RepostSleuthFrontend/1.0'
) -> Dict:
    """
    Debug OAuth token by making various Reddit API calls.
    
    Tests multiple endpoints to determine which scopes the token has.
    
    Args:
        token: Reddit OAuth access token
        subreddit: Name of the subreddit to test against
        user_agent: User agent string for requests
        
    Returns:
        Dictionary with results from each API test
    """
    headers = {'Authorization': f'Bearer {token}', 'User-Agent': user_agent}

    # Try to decode JWT to see embedded claims
    jwt_decoded = None
    try:
        if token.startswith('eyJ'):
            parts = token.split('.')
            if len(parts) >= 2:
                # Decode the payload (second part)
                payload = parts[1]
                # Add padding if needed
                padding = 4 - len(payload) % 4
                if padding != 4:
                    payload += '=' * padding
                decoded_bytes = base64.urlsafe_b64decode(payload)
                jwt_decoded = json_module.loads(decoded_bytes.decode('utf-8'))

                # Try to decode the scp (scopes) field if present
                if 'scp' in jwt_decoded and isinstance(jwt_decoded['scp'], str):
                    try:
                        scp_encoded = jwt_decoded['scp']
                        # Add padding if needed
                        scp_padding = 4 - len(scp_encoded) % 4
                        if scp_padding != 4:
                            scp_encoded += '=' * scp_padding
                        scp_bytes = base64.urlsafe_b64decode(scp_encoded)
                        # Try zlib decompress
                        try:
                            scp_decompressed = zlib.decompress(scp_bytes)
                            jwt_decoded['scp_decoded'] = scp_decompressed.decode('utf-8')
                        except:
                            # Maybe it's not compressed, try direct decode
                            jwt_decoded['scp_decoded'] = scp_bytes.decode('utf-8', errors='replace')
                    except Exception as e:
                        jwt_decoded['scp_decode_error'] = str(e)

                # Convert timestamps to readable format
                if 'iat' in jwt_decoded:
                    jwt_decoded['iat_readable'] = datetime.fromtimestamp(jwt_decoded['iat']).isoformat()
                if 'exp' in jwt_decoded:
                    jwt_decoded['exp_readable'] = datetime.fromtimestamp(jwt_decoded['exp']).isoformat()
    except Exception as e:
        jwt_decoded = {'decode_error': str(e)}

    results = {
        'user_agent_used': user_agent,
        'token_preview': f'{token[:10]}...{token[-5:]}' if len(token) > 15 else '[short token]',
        'token_length': len(token),
        'jwt_payload': jwt_decoded,
        'token_info': None,
        'mod_check': None,
        'scope_probe': {},
        'traffic_test': None,
        'modmail_test': None,
        'settings_test': None,
        'errors': []
    }
    
    # Test 1: Get user info from /api/v1/me (requires 'identity' scope)
    try:
        resp = requests.get('https://oauth.reddit.com/api/v1/me', headers=headers)
        results['scope_probe']['identity'] = resp.status_code == 200
        if resp.status_code == 200:
            me_data = resp.json()
            results['token_info'] = {
                'username': me_data.get('name'),
                'has_mod_access': me_data.get('is_mod', False),
                'oauth_client_id': me_data.get('oauth_client_id'),
                'raw_response': me_data
            }
        else:
            results['token_info'] = {
                'error': f'Status {resp.status_code}',
                'response': resp.text,
                'www_authenticate': resp.headers.get('www-authenticate')
            }
            results['errors'].append(f'/api/v1/me failed: {resp.status_code}')
    except Exception as e:
        results['token_info'] = {'error': str(e)}
        results['errors'].append(f'/api/v1/me exception: {e}')
    
    # Test 2: Check mysubreddits scope
    try:
        resp = requests.get('https://oauth.reddit.com/subreddits/mine/subscriber?limit=1', headers=headers)
        results['scope_probe']['mysubreddits'] = resp.status_code == 200
        if resp.status_code != 200:
            results['scope_probe']['mysubreddits_error'] = resp.headers.get('www-authenticate')
    except Exception as e:
        results['scope_probe']['mysubreddits'] = False
    
    # Test 3: Check read scope
    try:
        resp = requests.get(f'https://oauth.reddit.com/r/{subreddit}/about', headers=headers)
        results['scope_probe']['read'] = resp.status_code == 200
        if resp.status_code != 200:
            results['scope_probe']['read_error'] = resp.headers.get('www-authenticate')
    except Exception as e:
        results['scope_probe']['read'] = False
    
    # Test 4: Get moderator list and check user's mod permissions
    try:
        mod_url = f'https://oauth.reddit.com/r/{subreddit}/about/moderators'
        resp = requests.get(mod_url, headers=headers)
        if resp.status_code == 200:
            mod_data = resp.json()
            moderators = mod_data.get('data', {}).get('children', [])
            
            username = results['token_info'].get('username') if results['token_info'] else None
            user_mod_info = None
            if username:
                for mod in moderators:
                    if mod.get('name', '').lower() == username.lower():
                        user_mod_info = mod
                        break
            
            results['mod_check'] = {
                'is_moderator': user_mod_info is not None,
                'mod_permissions': user_mod_info.get('mod_permissions') if user_mod_info else None,
                'user_mod_info': user_mod_info,
                'total_mods': len(moderators)
            }
        else:
            results['mod_check'] = {
                'error': f'Status {resp.status_code}',
                'response': resp.text
            }
            results['errors'].append(f'/about/moderators failed: {resp.status_code}')
    except Exception as e:
        results['mod_check'] = {'error': str(e)}
        results['errors'].append(f'/about/moderators exception: {e}')
    
    # Test 5: Check modtraffic scope - this is the key test
    try:
        traffic_url = f'https://oauth.reddit.com/r/{subreddit}/about/traffic'
        resp = requests.get(traffic_url, headers=headers)
        www_auth = resp.headers.get('www-authenticate', '')
        results['scope_probe']['modtraffic'] = resp.status_code == 200
        results['traffic_test'] = {
            'status_code': resp.status_code,
            'success': resp.status_code == 200,
            'response': resp.text[:500] if len(resp.text) > 500 else resp.text,
            'www_authenticate': www_auth,
            'insufficient_scope': 'insufficient_scope' in www_auth.lower()
        }
        if resp.status_code != 200:
            results['errors'].append(f'/about/traffic failed: {resp.status_code} - {resp.text}')
    except Exception as e:
        results['traffic_test'] = {'error': str(e)}
        results['scope_probe']['modtraffic'] = False
        results['errors'].append(f'/about/traffic exception: {e}')
    
    # Test 6: Check modmail scope
    try:
        modmail_url = 'https://oauth.reddit.com/api/mod/conversations'
        resp = requests.get(modmail_url, headers=headers, params={'entity': subreddit})
        www_auth = resp.headers.get('www-authenticate', '')
        results['scope_probe']['modmail'] = resp.status_code == 200
        results['modmail_test'] = {
            'status_code': resp.status_code,
            'success': resp.status_code == 200,
            'response': resp.text[:200] if len(resp.text) > 200 else resp.text,
            'www_authenticate': www_auth,
            'insufficient_scope': 'insufficient_scope' in www_auth.lower()
        }
    except Exception as e:
        results['modmail_test'] = {'error': str(e)}
        results['scope_probe']['modmail'] = False
    
    # Test 7: Check modconfig scope
    try:
        settings_url = f'https://oauth.reddit.com/r/{subreddit}/about/edit'
        resp = requests.get(settings_url, headers=headers)
        www_auth = resp.headers.get('www-authenticate', '')
        results['scope_probe']['modconfig'] = resp.status_code == 200
        results['settings_test'] = {
            'status_code': resp.status_code,
            'success': resp.status_code == 200,
            'response': resp.text[:200] if len(resp.text) > 200 else resp.text,
            'www_authenticate': www_auth,
            'insufficient_scope': 'insufficient_scope' in www_auth.lower()
        }
    except Exception as e:
        results['settings_test'] = {'error': str(e)}
        results['scope_probe']['modconfig'] = False
    
    # Build summary of detected scopes
    detected_scopes = [scope for scope, has_it in results['scope_probe'].items() 
                       if has_it is True and not scope.endswith('_error')]
    missing_scopes = [scope for scope, has_it in results['scope_probe'].items() 
                      if has_it is False and not scope.endswith('_error')]
    
    results['scope_summary'] = {
        'detected_scopes': detected_scopes,
        'missing_scopes': missing_scopes
    }
    
    # Summary analysis
    results['analysis'] = _analyze_debug_results(results)
    
    return results


def _analyze_debug_results(results: Dict) -> Dict:
    """Analyze debug results and provide diagnostic summary."""
    analysis = {
        'likely_issues': [],
        'recommendations': []
    }
    
    # Check if token is valid at all
    if results.get('token_info', {}).get('error'):
        analysis['likely_issues'].append('Token appears invalid or expired')
        analysis['recommendations'].append('Request a new OAuth token from the user')
        return analysis
    
    # Check scope summary
    scope_summary = results.get('scope_summary', {})
    missing = scope_summary.get('missing_scopes', [])
    detected = scope_summary.get('detected_scopes', [])
    
    if 'modtraffic' in missing:
        analysis['likely_issues'].append(f'Token is MISSING modtraffic scope')
        analysis['likely_issues'].append(f'Token has these scopes: {detected}')
        analysis['recommendations'].append('The OAuth authorization must include "modtraffic" in the scope parameter')
        analysis['recommendations'].append('User must re-authorize to get a new token with the required scope')
        analysis['recommendations'].append('Check if the frontend is caching an old token')
    
    if 'modmail' in missing:
        analysis['likely_issues'].append('Token is also missing modmail scope')
    
    # Check mod status
    mod_check = results.get('mod_check', {})
    if mod_check.get('error'):
        analysis['likely_issues'].append('Could not verify moderator status')
    elif not mod_check.get('is_moderator'):
        analysis['likely_issues'].append('User is not a moderator of this subreddit')
        analysis['recommendations'].append('User must be a moderator to access traffic stats')
    else:
        # Check specific mod permissions
        perms = mod_check.get('mod_permissions', [])
        if perms is not None:
            if 'all' not in perms and 'traffic' not in perms:
                analysis['likely_issues'].append(f'User lacks "traffic" mod permission. Has: {perms}')
                analysis['recommendations'].append('Grant "traffic" permission to this moderator')
    
    # Check traffic test for specific error info
    traffic = results.get('traffic_test', {})
    if traffic.get('insufficient_scope'):
        if 'modtraffic' not in analysis['likely_issues'][0] if analysis['likely_issues'] else True:
            analysis['likely_issues'].append('Reddit confirmed insufficient_scope in www-authenticate header')
    
    if not analysis['likely_issues']:
        if traffic.get('success'):
            analysis['likely_issues'].append('No issues detected - traffic endpoint working!')
        else:
            analysis['likely_issues'].append('Unknown issue - traffic failed but no clear cause')
    
    return analysis
