import os
import redis
import urlparse
from werkzeug.wrappers import Request, Response
from werkzeug.routing import Map, Rule
from werkzeug.exceptions import HTTPException, NotFound
from werkzeug.wsgi import SharedDataMiddleware
from werkzeug.utils import redirect
from jinja2 import Environment, FileSystemLoader

class DataProviderDictionary(object):

	def __init__(self):
		self.data = {}

	def get(self, key):
		value = self.data.get(key)
##		print '[DataProviderDictionary] key=%s value=%s\n data=%s' % (key,
##																	value,
##																	self.data)
		return value

	def set(self, key, value):
		self.data[key] = value

	def incr(self, key):
		value = self.data.get(key, -1)
		value += 1
		self.data[key] = value
		return value

class DataProviderRedis(object):

	def __init__(self, redis_host, redis_port):
		redis = redis.Redis(redis_host, redis_port)

	def get(self, key):
		return self.redis.get(key)

	def set(self, key, value):
		self.redis.set(key, value)

	def incr(self, key):
		return self.redis.incr(key)

class Shortly(object):

	def __init__(self, config):
##		self.storage = DataProviderRedis(config['redis_host'], config['redis_port'])
		self.storage = DataProviderDictionary()
		template_path = os.path.join(os.path.dirname(__file__), 'templates')
		self.jinja_env = Environment(loader=FileSystemLoader(template_path),
									autoescape=True)
		self.url_map = Map([
			Rule('/', endpoint='new_url'),
			Rule('/<short_id>', endpoint='follow_short_link'),
			Rule('/<short_id>+', endpoint='short_link_details')
		])

 	def render_template(self, template_name, **context):
 		t = self.jinja_env.get_template(template_name)
 		return Response(t.render(context), mimetype='text/html')

	def dispatch_request(self, request):
		adapter = self.url_map.bind_to_environ(request.environ)
		try:
			endpoint, values = adapter.match()
			return getattr(self, 'on_' + endpoint)(request, **values)
		except HTTPException, e:
			return e

	def wsgi_app(self, environ, start_response):
		request = Request(environ)
		response = self.dispatch_request(request)
		return response(environ, start_response)

	def __call__(self, environ, start_response):
		return self.wsgi_app(environ, start_response)

	def insert_url(self, url):
		short_id = self.storage.get('reverse-url:' + url)
		if short_id is not None:
			return short_id
		url_num = self.storage.incr('last-url-id')
		short_id = base36_encode(url_num)
		self.storage.set('url-target:' + short_id, url)
		self.storage.set('reverse-url:' + url, short_id)
		return short_id
#Views---------------------------------------------------------------------
	def on_new_url(self, request):
		error = None
		url = ''
		if request.method == 'POST':
			url = request.form['url']
			if not is_valid_url(url):
				error = 'Please enter a valid URL'
			else:
				short_id = self.insert_url(url)
				return redirect('/%s+' % short_id)
		return self.render_template('new_url.html', error=error, url=url)

	def on_follow_short_link(self, request, short_id):
		link_target = self.storage.get('url-target:' + short_id)
		if link_target is None:
			raise NotFound()
		self.storage.incr('click-count:' + short_id)
		return redirect(link_target)

	def on_short_link_details(self, request, short_id):
		link_target = self.storage.get('url-target:' + short_id)
		if link_target is None:
			print self.storage.data
			raise NotFound()
		click_count = int(self.storage.get('click-count:' + short_id) or 0)
		return self.render_template('short_link_details.html',
									link_target=link_target,
									short_id=short_id,
									click_count=click_count)
#--------------------------------------------------------------------------

def base36_encode(number):
	assert number >= 0, 'positive integer required'
	if number == 0:
		return '0'
	base36 = []
	while number != 0:
		number, i = divmod(number, 36)
		base36.append('0123456789abcdefghijklmnopqrstuvwxyz'[i])
	return ''.join(reversed(base36))

def is_valid_url(url):
	parts = urlparse.urlparse(url)
	return parts.scheme in ('http', 'https')

def create_app(redis_host='localhost', redis_port=6379, with_static=True):
	app = Shortly({
		'redis_host':	redis_host,
		'redis_port':	redis_port
	})
	if with_static:
		app.wsgi_app = SharedDataMiddleware(app.wsgi_app, {
			'/static': os.path.join(os.path.dirname(__file__), 'static')
		})
	return app

if __name__ == '__main__':
	from werkzeug.serving import run_simple
	app = create_app()
	run_simple('0.0.0.0', 5000, app, use_debugger=True, use_reloader=True)