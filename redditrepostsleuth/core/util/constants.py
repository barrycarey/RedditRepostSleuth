USER_AGENTS = [
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/72.0.3626.81 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:53.0) Gecko/20100101 Firefox/53.0',
    'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.75.14 (KHTML, like Gecko) Version/7.0.3 Safari/7046A19',
    'Mozilla/5.0 (iPad; CPU OS 6_0 like Mac OS X) AppleWebKit/536.26 (KHTML, like Gecko) Version/6.0 Mobile/10A5355d Safari/8536.25'
]

GENERIC_REQ_HEADERS = {
	'Accept': '*/*',
	'Accept-Encoding': 'gzip, deflate, br',
	'Accept-Language': 'en-US,en;q=0.5',
	'Connection': 'keep-alive',
	'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36"
}


IGNORE_NO_MOD = [
    'DankMemes',
    'BlackPeopleTwitter',
    'cosplay',
    'whatisthissnake',

]

NO_LINK_SUBREDDITS = [
    'MurderedByWords',
    'goddesses',
    'NatureIsFuckingLit',
    'me_irl',
    'natureismetal',
    'interestingasfuck',
    'science',
    'madlads',
    'tumblr',
    'interestingasfuck',
    'art',
    'eyebleach',
    'facepalm'

]

ONLY_COMMENT_REPOST_SUBS = [
    'gaming',
    'dankmemes'
]

SILENCED_SUBS = [
    'dankmemes'
]

BANNED_SUBS = [
    'wholesomememes',
    'blursedimages',
    'ginger',
    'gonewild',
    'murderedbywords',
    'confusing_perspective',
    'suspiciouslyspecific',
    'festivalsluts',
    'cursedcomments',
    'badphilosophy',
    'fakehistoryporn',
    'suomi',
    'dataisbeautiful',
    'rareinsults',
    'atbge',
    'cyberpunkgame',
    'earth_is_level',
    'oldschoolcool',
    'warframe',
    'elitedangerous',
    'smashbrosultimate',
    'food',
    'toptalent',
    'gamingcirclejerk',
    'wizardsunite',
    'comedyheaven',
    'bonehurtingjuice',
    'bassoon',
    'antiwork',
    'ik_ihe',
    'gamersriseup',
    'comedynecromancy',
    'belgium',
    'norge',
    'wellthatsucks',
    'boottoobig',
    'politics',
    'electronics',
    'whatisthisthing',
    'justneckbeardthings',
    'whatisthisthing',
    'pewdiepiesubmissions',
    'oddlysatisfying',
    'cursedimages',
    'minecraft',
    'oregairusnafu'
    'fireemblem',
    'hmmm'
    'jokes'
    'clevercomebacks',
    'pcmasterrace',
    'news',
    'physics',
    'modernwarfare',
    'purrito',
    'gaming',
    'petitegonewild',
    'celebnsfw',
    'geek',
    'absolutelynotanimeirl',
    'callofduty',
    'photoshopbattles',
    'teenagers',
    'blizzard',
    'imaginarymonsters',
    'insaneparents',
    'comedycemetery',
    'cirkeltrek',
    'pics',
    'funny',
    'geekygirls',
    'csgo',
    'deadbydaylight',
    'csgo',
    'trashpandas',
    'dontputthatinyourass',
    'crappydesign',
    'ohitllbefine',
    'introvert',
    'thebullwins',
    'delicioustraps',
    'halloween',
    'de',
    'BlackPeopleTwitter'

]

CUSTOM_FILTER_LEVELS = {
    'memes': {
        'annoy': None,
        'hamming': 3
    },
    'dankmemes': {
        'annoy': None,
        'hamming': 3
    },
    'historymemes': {
        'annoy': None,
        'hamming': 2
    },
    'prequelmemes': {
        'annoy': None,
        'hamming': 2
    },
    'historymemes': {
        'annoy': None,
        'hamming': 1
    }
}