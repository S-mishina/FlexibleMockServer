from flask import Flask, jsonify, make_response, Response, request
from logging.config import dictConfig
from jsonschema import validate
import time
import os
import yaml
import sys
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.zipkin.json import ZipkinExporter
from opentelemetry.semconv.resource import ResourceAttributes

def get_yaml_file_path():
    return os.getenv('CUSTOM_RULE_YAML_FILE', 'config/custom_rule.yaml')

def get_open_telemetry_flg():
    return os.getenv('OPEN_TELEMETRY_FLG', 'True')

def get_file_check(yaml_file,log_flag):
    if not os.path.exists(yaml_file):
        if log_flag==True:
            app.logger.info("{} not found".format(yaml_file))
        return False
    else:
        if log_flag==True:
            app.logger.info("{} file check ok".format(yaml_file))
        return True

def config_check(yaml_file):
    with open(yaml_file, "r") as yaml_file:
        yaml_data = yaml.safe_load(yaml_file)
    try:
        validate(instance=yaml_data, schema=schema)
        app.logger.info("The YAML file is consistent with the schema.")
        for i in range(len(yaml_data["custom_rule"])):
            try:
                with open(yaml_data["custom_rule"][i]["rule"].get("response_body_path"), "r") as response_body_file:
                    response_body = response_body_file.read()
            except Exception as e:
                app.logger.info("response_body_path not found: %s" % str(e))
                sys.exit(1)
    except Exception as e:
        app.logger.info("YAML file does not match schema: %s" % str(e))
        sys.exit(1)

def check_open_telemetry():
    if get_open_telemetry_flg():
        if os.getenv('OTEL_SERVICE_NAME') is None:
            os.environ['OTEL_SERVICE_NAME'] = 'mock-server'
        if os.getenv('OPEN_TELEMETRY_ZIPKIN_FLG', 'False') == 'True':
            zipkin_exporter = ZipkinExporter(endpoint=os.getenv('ZIPKIN_HOST', 'http://localhost:9411/api/v2/spans'))
            provider = TracerProvider()
            processor = BatchSpanProcessor(zipkin_exporter)
            provider.add_span_processor(processor)
            trace.set_tracer_provider(provider)
        else:
            provider = TracerProvider()
            processor = BatchSpanProcessor(ConsoleSpanExporter())
            provider.add_span_processor(processor)
            trace.set_tracer_provider(provider)
            tracer = trace.get_tracer("my.tracer.name")


dictConfig({
    'version': 1,
    'formatters': {
        'default': {
            'format': '[%(asctime)s] in %(module)s: %(message)s',
        }
    },
    'handlers': {
        'wsgi': {
            'class': 'logging.StreamHandler',
            'stream': 'ext://flask.logging.wsgi_errors_stream',
            'formatter': 'default'
        }
    },
    'root': {
        'level': 'INFO',
        'handlers': ['wsgi']
    }
})

host = os.environ.get('HOST', '0.0.0.0')
port = os.environ.get('PORT', 8080)
app = Flask(__name__)

if get_open_telemetry_flg() == 'True':
    check_open_telemetry()
    FlaskInstrumentor().instrument_app(app)

HTTP_METHODS = ['GET', 'HEAD', 'POST', 'PUT',
                'DELETE', 'CONNECT', 'OPTIONS', 'TRACE', 'PATCH']
yaml_file = 'config/custom_rule.yaml'
schema = {
    "type": "object",
    "properties": {
        "custom_rule": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "rule": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "method": {"type": "string"},
                            "sleep_time": {"type": "integer", "minimum": 0},
                            "status_code": {"type": "integer", "minimum": 100, "maximum": 599},
                            "response_body_path": {"type": "string"},
                            "response_header": {"type": "string"}
                        },
                        "required": ["path", "method", "status_code"],
                        "additionalProperties": False
                    }
                },
                "required": ["name", "rule"],
                "additionalProperties": False
            }
        }
    },
    "required": ["custom_rule"],
    "additionalProperties": False
}


@app.before_request
def before_request():
    request.start_time = time.time()

@app.after_request
def after_request(response):
    latency = time.time() - request.start_time
    response_log = {
        "path": request.path,
        "method": request.method,
        "status_code": response.status_code,
        "response_time": latency,
        "request_header": dict(request.headers),
        "response_header": dict(response.headers),
        "query_params": request.args.to_dict(),
    }
    app.logger.info(response_log)
    return response

host = os.environ.get('HOST', '0.0.0.0')
port = os.environ.get('PORT', 8080)

@app.route('/')
def top():
    return make_response(jsonify(top='Hello mock server'), 200)

@app.route('/<int:sleep_time>/<int:status_code>', methods=HTTP_METHODS)
@app.route('/<int:sleep_time>/<int:status_code>/', methods=HTTP_METHODS)
def index(sleep_time, status_code):
    if 100 <= status_code <= 599:
        time.sleep(sleep_time)
        return make_response(jsonify(sleep_time=sleep_time, status_code=status_code), status_code)
    else:
        return make_response(jsonify(err="Not status code"), 400)

@app.route('/sleep/<int:sleep_time>', methods=HTTP_METHODS)
@app.route('/sleep/<int:sleep_time>/', methods=HTTP_METHODS)
def only_sleep_time(sleep_time):
    time.sleep(sleep_time)
    return make_response(jsonify(sleep_time=sleep_time, status_code=200), 200)

@app.route('/status/<int:status_code>', methods=HTTP_METHODS)
@app.route('/status/<int:status_code>/', methods=HTTP_METHODS)
def only_status_code(status_code, sleep_time=0):
    if 100 <= status_code <= 599:
        time.sleep(sleep_time)
        return make_response(jsonify(sleep_time=sleep_time, status_code=status_code), status_code)
    else:
        return make_response(jsonify(err="Not status code"), 400)

@app.route('/<int:sleep_time>/<int:status_code>/query', methods=HTTP_METHODS)
def index_query(sleep_time, status_code):
    if 100 <= status_code <= 599:
        time.sleep(sleep_time)
        query_params_dict = request.args.to_dict()
        return make_response(jsonify(sleep_time=sleep_time, status_code=status_code, output=str(query_params_dict)), status_code)
    else:
        return make_response(jsonify(err="Not status code"), 400)


@app.route('/sleep/<int:sleep_time>/query', defaults={'status_code': 200}, methods=HTTP_METHODS)
def only_sleep_time_query(sleep_time, status_code):
    time.sleep(sleep_time)
    query_params_dict = request.args.to_dict()
    return make_response(jsonify(sleep_time=sleep_time, status_code=status_code, output=str(query_params_dict)), status_code)


@app.route('/status/<int:status_code>/query', methods=HTTP_METHODS)
def only_status_code_query(status_code, sleep_time=0):
    if 100 <= status_code <= 599:
        time.sleep(sleep_time)
        query_params_dict = request.args.to_dict()
        return make_response(jsonify(sleep_time=sleep_time, status_code=status_code, output=str(query_params_dict)), status_code)
    else:
        return make_response(jsonify(err="Not status code"), 400)

@app.route('/<path:path>', methods=HTTP_METHODS)
def custom_rule(path):
    yaml_file = get_yaml_file_path()
    file_flag=get_file_check(yaml_file,False)
    if file_flag==False:
        return make_response(404)
    path = '/' + path
    with open(yaml_file, "r") as yaml_file:
        yaml_data = yaml.safe_load(yaml_file)
    for i in range(len(yaml_data["custom_rule"])):
        if yaml_data["custom_rule"][i]["rule"]["path"] == path and yaml_data["custom_rule"][i]["rule"]["method"] == request.method:
            if response_body_pathx := yaml_data["custom_rule"][i]["rule"].get("response_body_path"):
                try:
                    with open(response_body_pathx, "r") as response_body_file:
                        response_body = response_body_file.read()
                        if sleep_time := yaml_data["custom_rule"][i]["rule"].get("sleep_time"):
                            time.sleep(sleep_time)
                    return make_response(jsonify(response_body), yaml_data["custom_rule"][i]["rule"]["status_code"])
                except Exception as e:
                    app.logger.info(e)
                    return make_response(jsonify(status=500), 500)
    return make_response(jsonify(status=500), 500)

@app.route('/favicon.ico')
def favicon():
    return '', 204  # 空のレスポンスで204 No Contentを返す

@app.errorhandler(404)
def page_not_found(e):
    return make_response(404)

if __name__ == '__main__':
    yaml_file = get_yaml_file_path()
    file_flag=get_file_check(yaml_file,True)
    app.logger.info("file_flag: %s" % file_flag)
    if file_flag==True:
        config_check(yaml_file)
    app.run(host=host, port=port)
