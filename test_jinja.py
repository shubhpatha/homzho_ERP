from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader('templates'))
try:
    template = env.get_template('base.html')
    print("base.html parsed successfully!")
except Exception as e:
    import traceback
    traceback.print_exc()

try:
    template = env.get_template('login.html')
    print("login.html parsed successfully!")
except Exception as e:
    import traceback
    traceback.print_exc()
