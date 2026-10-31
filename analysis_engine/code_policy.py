"""Validate the bounded analyst wrapper before isolated execution."""
import ast
from analysis_engine.ingestion import InputError


def validate_forecast_program(code):
    # shortcut: forecast wrappers only; add evaluated recipe capabilities before broadening generated Python.
    try:
        tree=ast.parse(code)
    except SyntaxError as exc:
        raise InputError('The analysis program is not valid Python.','code_rejected') from exc
    aliases={}
    permitted={'json','types','vds_recipe'}
    for node in ast.walk(tree):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef,ast.Lambda,ast.For,ast.While,ast.Delete,ast.Global,ast.Nonlocal)):
            raise InputError('The program exceeds the approved recipe wrapper.','code_rejected')
        if isinstance(node,ast.Import):
            for name in node.names:
                if name.name not in permitted:raise InputError('The program requests an unapproved import.','code_rejected')
                aliases[name.asname or name.name]=name.name
        if isinstance(node,ast.ImportFrom):
            if node.module not in permitted or node.level:
                raise InputError('The program requests an unapproved import.','code_rejected')
            for name in node.names:
                full=node.module+'.'+name.name
                if full not in {'types.SimpleNamespace','vds_recipe.forecast_result','json.load','json.loads','json.dumps'}:
                    raise InputError('The program requests an unapproved capability.','code_rejected')
                aliases[name.asname or name.name]=full
        if isinstance(node,ast.Attribute) and node.attr.startswith('_'):
            raise InputError('Private runtime access is not permitted.','code_rejected')
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Attribute) for t in node.targets):
            raise InputError('The program cannot alter runtime attributes.','code_rejected')
    for node in ast.walk(tree):
        if isinstance(node,ast.Name) and (node.id.startswith("__") or (isinstance(node.ctx,ast.Store) and node.id in set(aliases)|{"open","print"})):
            raise InputError("The program cannot replace approved runtime capabilities.","code_rejected")
    def name(node):
        if isinstance(node,ast.Name):return aliases.get(node.id,node.id)
        if isinstance(node,ast.Attribute):return name(node.value)+'.'+node.attr
        return ''
    used_recipe=False
    for node in ast.walk(tree):
        if not isinstance(node,ast.Call):continue
        target=name(node.func)
        if target=='open':
            if not 1<=len(node.args)<=2 or not isinstance(node.args[0],ast.Constant) or node.args[0].value!='plan.json' or node.keywords or (len(node.args)>1 and (not isinstance(node.args[1],ast.Constant) or node.args[1].value not in {'r','rt'})):
                raise InputError('Only the approved plan file may be read.','code_rejected')
        elif target in {'json.load','json.loads'} and node.keywords:
            raise InputError('JSON callback hooks are not permitted.','code_rejected')
        elif target=='json.dumps' and any(k.arg not in {'indent','allow_nan','sort_keys'} for k in node.keywords):
            raise InputError('JSON callback hooks are not permitted.','code_rejected')
        elif target=='vds_recipe.forecast_result':
            if not node.args or not isinstance(node.args[0],ast.Constant) or node.args[0].value!='dataset.parquet':
                raise InputError('The program must use the approved dataset.','code_rejected')
            used_recipe=True
        elif target not in {'print','json.load','json.loads','json.dumps','types.SimpleNamespace'}:
            raise InputError('The program requests an unapproved operation.','code_rejected')
    if not used_recipe:raise InputError('The approved analytical recipe was not called.','code_rejected')
    return code
