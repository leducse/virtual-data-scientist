"""Validate the bounded analyst wrapper before isolated execution."""
import ast
from analysis_engine.ingestion import InputError


def validate_forecast_program(code, recipe="forecast_result"):
    if recipe not in {'forecast_result', 'supervised_result', 'unsupervised_result'}:
        raise InputError('Unapproved analytical recipe.', 'code_rejected')
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
                if full not in {'types.SimpleNamespace','vds_recipe.'+recipe,'json.load','json.loads','json.dumps'}:
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
        elif target=='vds_recipe.'+recipe:
            if not node.args or not isinstance(node.args[0],ast.Constant) or node.args[0].value!='dataset.parquet':
                raise InputError('The program must use the approved dataset.','code_rejected')
            used_recipe=True
        elif target not in {'print','json.load','json.loads','json.dumps','types.SimpleNamespace'}:
            raise InputError('The program requests an unapproved operation.','code_rejected')
    if not used_recipe:raise InputError('The approved analytical recipe was not called.','code_rejected')
    return code


def validate_sealed_program(code, example):
    """New ML wrappers cannot mutate plans, results or runtime state."""
    try:
        proposed, expected = ast.parse(code), ast.parse(example)
    except SyntaxError as exc:
        raise InputError('Invalid analysis wrapper.', 'code_rejected') from exc
    # Whitespace/comments and the file-handle variable may differ; operations may not.
    def normalized(tree):
        handles = {node.optional_vars.id for node in ast.walk(tree) if isinstance(node, ast.withitem) and isinstance(node.optional_vars, ast.Name)}
        class Handles(ast.NodeTransformer):
            def visit_Name(self, node):
                return ast.copy_location(ast.Name(id='source' if node.id in handles else node.id, ctx=node.ctx), node)
        return ast.dump(Handles().visit(tree), include_attributes=False)
    if normalized(proposed) != normalized(expected):
        raise InputError('Return the approved wrapper exactly; plans and analytical results cannot be edited.', 'code_rejected')
    return code
