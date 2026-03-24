"""YouTube research helpers for Project Dash."""
import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

def youtube_search(query, max_results=5, days_back=7):
    """Search YouTube for recent videos on a topic."""
    from dotenv import load_dotenv
    load_dotenv('/home/ra/projects/DuberyMNL/.env')
    key = os.environ.get('YOUTUBE_API_KEY')
    if not key:
        return {'error': 'No YOUTUBE_API_KEY in .env'}

    after = (datetime.utcnow() - timedelta(days=days_back)).strftime('%Y-%m-%dT00:00:00Z')
    params = urllib.parse.urlencode({
        'part': 'snippet',
        'q': query,
        'type': 'video',
        'order': 'date',
        'maxResults': max_results,
        'publishedAfter': after,
        'key': key
    })
    url = f'https://www.googleapis.com/youtube/v3/search?{params}'
    resp = urllib.request.urlopen(url)
    data = json.loads(resp.read())

    results = []
    for item in data.get('items', []):
        s = item['snippet']
        results.append({
            'video_id': item['id']['videoId'],
            'title': s['title'],
            'channel': s['channelTitle'],
            'date': s['publishedAt'][:10],
            'url': f"https://youtube.com/watch?v={item['id']['videoId']}"
        })
    return results


def youtube_transcript(video_id):
    """Pull transcript from a YouTube video."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id)
        text = ' '.join([t.text for t in transcript.snippets])
        return text
    except Exception as e:
        return f'Transcript unavailable: {e}'


if __name__ == '__main__':
    import sys
    query = ' '.join(sys.argv[1:]) or 'AI automation news 2026'
    print(f'Searching: {query}\n')
    results = youtube_search(query)
    for r in results:
        print(f"{r['date']} | {r['channel']}")
        print(f"  {r['title']}")
        print(f"  {r['url']}")
        print()
    if results:
        print('--- Transcript preview (first result) ---')
        t = youtube_transcript(results[0]['video_id'])
        print(t[:500] + '...' if len(t) > 500 else t)
