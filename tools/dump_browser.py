#!/usr/bin/python3

from collections import namedtuple, OrderedDict
from os import listdir, path
from html import escape
from http.server import HTTPServer, BaseHTTPRequestHandler
from importlib import import_module
from threading import Thread
import traceback
import re


PATH_PATTERN = re.compile('/([^./?]+)\.([^./?]+)\.([^./?]+)')


DumpDict = namedtuple('DumpDict', ['by_test', 'by_type'])
Dump = namedtuple('Dump', ['test', 'date', 'type'])


dump_name = '.'.join


def listdumps():
	for name in listdir():
		if path.isdir(name):
			continue
		try:
			yield Dump(*name.split('.'))
		except TypeError:
			# split didn't return 3-element array
			print('Warning: %r is not a valid dump name. Expected "test.date.type"' % name)


def newestdump():
	return min(listdumps(), key=lambda dump: dump.date)


def get_dump_dict():
	dumps = sorted(listdumps(), key=lambda dump: dump.date, reverse=True)

	by_test, by_type = OrderedDict(), OrderedDict()
	for dump in dumps:
		if dump.test not in by_test:
			by_test[dump.test] = OrderedDict()
		by_date = by_test[dump.test]

		if dump.date not in by_date:
			by_date[dump.date] = []
		by_date[dump.date].append(dump)

		if dump.type not in by_type:
			by_type[dump.type] = []
		by_type[dump.type].append(dump)

	return DumpDict(by_test, by_type)


def html_link(dump, text, existing):
	if dump in existing:
		yield '<li><a href="%s">%s</a></li>' % (dump_name(dump), text)
	else:
		yield '<li><a href="%s" style="color: darkred">%s</a></li>' % (dump_name(dump), text)


def html_by_test(by_test, current_dump):
	for test, by_date in by_test.items():
		yield '<b>%s</b><ul>' % test
		for date, dumps in by_date.items():
			yield from html_link(Dump(test, date, current_dump.type), date, dumps)
		yield '</ul>'


def html_by_type(by_type, current_dump):
	yield '<ul>'
	for type, dumps in by_type.items():
		yield from html_link(Dump(current_dump.test, current_dump.date, type), type, dumps)
	yield '</ul>'


def default_view(file, dump, params):
	yield '<div style="border: solid 2px black">No viewer for %r found.</div>' % dump.type
	yield '<pre style="background-color: lightgray">'
	yield escape(file.read())
	yield '</pre>'


def html_dump(dump, params):
	try:
		yield '<!doctype html><html><head><meta charset="utf8"><title>%s</title></head><body>' % dump_name(dump)

		dumps = get_dump_dict()
		yield '<div style="position: absolute; top: 0; bottom: 0; right: 0; width: 16em; overflow: auto"><div style="margin: 1em">'
		yield from html_by_test(dumps.by_test, dump)
		yield '<hr>'
		yield from html_by_type(dumps.by_type, dump)
		yield '</div></div>'

		yield '<div style="position: absolute; left: 0; top: 0; bottom: 0; right: 16em; overflow: auto"><div style="margin: 1em">'
		try:
			with open(dump_name(dump)) as file:
				try:
					view = import_module('viewers.' + dump.type).view
				except ImportError:
					view = default_view
				yield from view(file, dump, params)
		except FileNotFoundError:
			yield '<div style="border: solid 2px black">Dump %r not found.</div>' % dump_name(dump)
		yield '</div></div>'

		yield '</body></html>'
	except Exception as e:
		yield '<br>... crashed with %r. See console.' % e
		traceback.print_exc()


class DumpBrowserHTTPRequestHandler(BaseHTTPRequestHandler):
	def do_GET(self):
		if '?' in self.path:
			file, params_str = self.path.split('?', 1)
		else:
			file, params_str = self.path, ''
		params = dict(param.split('=', 1) for param in params_str.split('&') if '=' in param)

		if file == '/':
			self.send_response(302)
			self.send_header('Location', self.absolute(dump_name(newestdump()) + '?index'))
			self.end_headers()
			return

		if file == '/STOP':
			self.send_response(200)
			self.send_header('Content-Type', 'text/plain')
			self.end_headers()
			self.wfile.write(b'Stopping')
			Thread(target=self.server.shutdown).start()
			return

		mo = PATH_PATTERN.fullmatch(file)
		if mo:
			self.send_response(200)
			self.send_header('Content-Type', 'text/html')
			self.end_headers()
			self.wfile.writelines(bytes(line, 'utf-8') for line in html_dump(Dump(*mo.group(1, 2, 3)), params))
			return

		self.send_response(400)
		self.send_header('Content-Type', 'text/plain')
		self.end_headers()
		self.wfile.write(b'Invalid URL')

	def absolute(self, s):
		return 'http://' + self.headers['Host'] + '/' + s


HTTPServer(('localhost', 8000), DumpBrowserHTTPRequestHandler).serve_forever()
