"""Fixed-origin read-only public creator API. No update/delete or general HTTP tool."""
import json
import math
import os
import re
from urllib.parse import quote, urlencode
from urllib.request import Request, HTTPRedirectHandler, build_opener

BASE = 'https://samaj.getwyld.in/api/public/v1'
USERNAME = re.compile(r'[A-Za-z0-9._]{1,30}')
MAX_BYTES = 2_000_000

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

_open = build_opener(NoRedirect()).open


def username(value):
    if not isinstance(value,str) or not USERNAME.fullmatch(value) or value in ('.','..'):
        raise ValueError('Invalid creator username')
    return value.lower()


def pagination(page,page_size):
    if type(page) is not int or not 1<=page<=1000 or type(page_size) is not int or not 1<=page_size<=25:
        raise ValueError('Page must be 1–1000 and page size 1–25')


def _request(method,path,*,params=None,payload=None):
    # Defense in depth: helpers cannot turn into an arbitrary method/URL transport.
    valid = (method=='GET' and path=='/creators') or (method=='POST' and path=='/creators/search')
    if method=='GET' and path.startswith('/creators/'):
        raw=path.removeprefix('/creators/')
        valid=bool(USERNAME.fullmatch(raw)) and raw not in ('.','..','search')
    if not valid:raise ValueError('Only reviewed creator read endpoints are allowed')
    if params is not None and (method!='GET' or path!='/creators' or set(params)!={'page','page_size'}):raise ValueError('Invalid read query parameters')
    if params is not None:pagination(params['page'],params['page_size'])
    if method=='GET' and payload is not None:raise ValueError('GET cannot carry a request body')
    if method=='POST':
        if not isinstance(payload,dict) or set(payload)!={'query','page','page_size','filters'}:
            raise ValueError('Invalid search request')
        pagination(payload['page'],payload['page_size'])
        if not isinstance(payload['query'],str) or not 1<=len(payload['query'].strip())<=200:
            raise ValueError('Invalid search query')
        filters=payload['filters']
        if not isinstance(filters,dict) or not set(filters)<= {'followers_min','engagement_rate_min'}:
            raise ValueError('Invalid search filters')
        for name,value in filters.items():
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
                raise ValueError('Invalid search filter')
            if name=='followers_min' and (type(value) is not int or value>10**12):
                raise ValueError('Invalid followers filter')
            if name=='engagement_rate_min' and value>100:
                raise ValueError('Invalid engagement filter')
    key=os.getenv('WYLD_API_KEY','')
    if not key or any(c in key for c in '\r\n'):raise RuntimeError('Enter WYLD_API_KEY locally before using the public creator API')
    url=BASE+path+('?' + urlencode(params) if params else '')
    request=Request(url,data=json.dumps(payload).encode() if payload is not None else None,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','Accept':'application/json'},method=method)
    try:
        with _open(request,timeout=12) as response:
            if getattr(response,'status',200)!=200:raise ValueError('Unexpected response status')
            # Redirects are refused by the opener; final origin/path must still be identical.
            if hasattr(response,'geturl') and response.geturl()!=url:raise ValueError('Redirect refused')
            raw=response.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:raise ValueError('Oversized response')
        data=json.loads(raw)
        if not isinstance(data,dict):raise ValueError('Invalid response envelope')
        if key in json.dumps(data,ensure_ascii=False):raise ValueError('Credential reflected in provider response')
        return data
    except Exception:
        # Never surface provider response bodies, URLs, headers or credential-bearing exceptions.
        raise RuntimeError('Public creator API unavailable or response invalid; verify local access and provider schema') from None


def profile_fields(item):
    if not isinstance(item,dict):raise ValueError('Invalid creator record')
    result={'username':username(item.get('username'))}
    for field in ('full_name','creator_location','content_quality_summary'):
        value=item.get(field)
        if value is not None and not isinstance(value,str):raise ValueError('Invalid creator text field')
        result[field]=value[:1500] if value is not None else None
    for field in ('followers_count','engagement_rate','fit_score'):
        value=item.get(field)
        if value is not None:
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:raise ValueError('Invalid creator metric')
            if field=='followers_count' and (not isinstance(value,int) or value>10**12):raise ValueError('Invalid follower count')
            if field!='followers_count' and value>100:raise ValueError('Invalid creator percentage')
        result[field]=value
    reasons=item.get('match_reasons')
    if reasons is not None and (not isinstance(reasons,list) or not all(isinstance(x,str) for x in reasons)):raise ValueError('Invalid creator reasons')
    result['match_reasons']=[x[:500] for x in (reasons or [])[:20]]
    return result


def collection(data,page,page_size,endpoint):
    try:
        envelope=data.get('data',data)
        if not isinstance(envelope,dict) or not isinstance(envelope.get('items'),list):raise ValueError('Unsupported collection schema')
        total=envelope.get('total')
        if type(total) is not int or total<0:raise ValueError('Invalid total')
        if len(envelope['items'])>page_size:raise ValueError('Page exceeds requested size')
        items=[profile_fields(item) for item in envelope['items']]
        return {'source':'Wyld Samaj public API '+endpoint,'verified_response':True,'insights_verified':False,'page':page,'page_size':page_size,'total':total,'items':items}
    except Exception:
        raise RuntimeError('Public creator API returned an unsupported or invalid creator schema') from None


def list_creators(page=1,page_size=25):
    pagination(page,page_size)
    return collection(_request('GET','/creators',params={'page':page,'page_size':page_size}),page,page_size,'GET /creators')


def get_creator(handle):
    handle=username(handle)
    if handle=='search':raise ValueError('Reserved creator path')
    data=_request('GET','/creators/'+quote(handle,safe=''))
    try:
        item=data.get('data',data)
        if isinstance(item,dict) and 'creator' in item:item=item['creator']
        item=profile_fields(item)
        if item['username']!=handle:raise ValueError('Mismatched profile identity')
        return {'source':'Wyld Samaj public API GET /creators/{username}','verified_response':True,'insights_verified':False,'creator':item}
    except Exception:raise RuntimeError('Public creator API returned an unsupported or mismatched profile') from None


def search(query,page=1,page_size=25,filters=None):
    pagination(page,page_size)
    if not isinstance(query,str) or not 1<=len(query.strip())<=200:raise ValueError('Search query must be 1–200 characters')
    filters={} if filters is None else filters
    if not isinstance(filters,dict) or not set(filters)<= {'followers_min','engagement_rate_min'}:raise ValueError('Unsupported search filter')
    for name,value in filters.items():
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:raise ValueError('Invalid search filter')
        if name=='followers_min' and (type(value) is not int or value>10**12):raise ValueError('Invalid followers filter')
        if name=='engagement_rate_min' and value>100:raise ValueError('Invalid engagement filter')
    body={'query':query.strip(),'page':page,'page_size':page_size,'filters':filters}
    return collection(_request('POST','/creators/search',payload=body),page,page_size,'POST /creators/search')
