import json
import sys
import subprocess
import hashlib
import os

def calculate_hash(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest(), os.path.getsize(path)

def get_tracked_python_files():
    out = subprocess.check_output(['git', 'ls-files', '*.py']).decode('utf-8')
    return set(x.strip() for x in out.splitlines() if x.strip())

def is_active(path):
    lower = path.lower()
    return not ('legacy' in lower or 'archive' in lower or 'deprecated' in lower)

def analyze_graph(path):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    nodes = data.get('nodes', [])
    edges = data.get('links', [])
    
    node_count = len(nodes)
    edge_count = len(edges)
    communities = len(set(n.get('community') for n in nodes if n.get('community') is not None))
    
    extracted = 0
    inferred = 0
    ambiguous = 0
    
    for e in edges:
        t = e.get('type')
        if t == 'INFERRED':
            inferred += 1
        elif t == 'AMBIGUOUS':
            ambiguous += 1
        else:
            extracted += 1
            
        # check confidence values
        if 'confidence' in e:
            conf = e['confidence']
            if conf not in ('EXTRACTED', 'INFERRED') and not isinstance(conf, (int, float)):
                raise ValueError(f"Invalid confidence value: {conf}")

    py_files = set()
    absolute_paths = []
    secrets_found = []
    
    secret_patterns = ['ghp_', 'AKIA', 'sk-ant-', 'sk-proj-']
    
    for n in nodes:
        sf = n.get('source_file', '')
        if sf:
            if sf.startswith('/') or ':\\' in sf:
                absolute_paths.append(sf)
            if sf.endswith('.py'):
                py_files.add(sf)
                
        # Check node labels/contents for real secrets
        content = json.dumps(n)
        for sp in secret_patterns:
            if sp in content:
                secrets_found.append(sp)

    return {
        'nodes': node_count,
        'edges': edge_count,
        'communities': communities,
        'extracted': extracted,
        'inferred': inferred,
        'ambiguous': ambiguous,
        'py_files': py_files,
        'absolute_paths': absolute_paths,
        'secrets_found': secrets_found
    }

def main():
    try:
        active_path = 'graphify-out/active/graph.json'
        full_path = 'graphify-out/graph.json'
        
        active_hash, active_size = calculate_hash(active_path)
        full_hash, full_size = calculate_hash(full_path)
        
        active_stats = analyze_graph(active_path)
        full_stats = analyze_graph(full_path)
        
        tracked_py = get_tracked_python_files()
        active_tracked = {f for f in tracked_py if is_active(f)}
        
        # Check source commit exact
        head_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode('utf-8').strip()
        if head_commit != 'a1f5c69224e1f6ec8e2327ec4fe151a4ce1bd21a':
            print(f"FAIL: Expected commit a1f5c69224e1f6ec8e2327ec4fe151a4ce1bd21a, got {head_commit}")
            sys.exit(1)
            
        # every tracked active Python file is represented in the active graph
        missing_active = active_tracked - active_stats['py_files']
        if missing_active:
            print(f"FAIL: Missing active tracked files in active graph: {missing_active}")
            sys.exit(1)
            
        # no legacy or archived path exists in the active graph
        legacy_in_active = {f for f in active_stats['py_files'] if not is_active(f)}
        if legacy_in_active:
            print(f"FAIL: Legacy files found in active graph: {legacy_in_active}")
            sys.exit(1)
            
        # full graph retains archived/legacy coverage
        legacy_in_full = {f for f in full_stats['py_files'] if not is_active(f)}
        if not legacy_in_full:
            print(f"FAIL: Full graph missing legacy coverage")
            sys.exit(1)
            
        if active_stats['absolute_paths']:
            print(f"FAIL: Absolute paths in active graph: {active_stats['absolute_paths']}")
            sys.exit(1)
            
        if full_stats['absolute_paths']:
            print(f"FAIL: Absolute paths in full graph: {full_stats['absolute_paths']}")
            sys.exit(1)
            
        if active_stats['secrets_found'] or full_stats['secrets_found']:
            print("FAIL: Secrets found in graphs")
            sys.exit(1)
            
        # Write validation record
        validation_record = {
            'base_branch': 'research/cycle-02-trend-pilot-02',
            'full_head': head_commit,
            'graphify_version': '0.9.29',
            'exact_commands': 'graphify extract D:\\Obsidian-RL-active --code-only; graphify cluster-only D:\\Obsidian-RL-active',
            'active_hash': active_hash,
            'active_size': active_size,
            'full_hash': full_hash,
            'full_size': full_size,
            'active_counts': {
                'nodes': active_stats['nodes'],
                'edges': active_stats['edges'],
                'communities': active_stats['communities'],
                'extracted': active_stats['extracted'],
                'inferred': active_stats['inferred'],
                'ambiguous': active_stats['ambiguous']
            },
            'full_counts': {
                'nodes': full_stats['nodes'],
                'edges': full_stats['edges'],
                'communities': full_stats['communities'],
                'extracted': full_stats['extracted'],
                'inferred': full_stats['inferred'],
                'ambiguous': full_stats['ambiguous']
            },
            'tracked_active_python_count': len(active_tracked),
            'represented_active_files': len(active_stats['py_files']),
            'missing_active_files': len(missing_active),
            'excluded_lifecycle_paths': len(legacy_in_active),
            'absolute_path_findings': 0,
            'secret_scan_findings': 0,
            'validator_exit_code': 0,
            'limitations': 'Graph is navigation, not financial verification.'
        }
        
        with open('graphify-out/GRAPH_VALIDATION.json', 'w', encoding='utf-8') as f:
            json.dump(validation_record, f, indent=2)
            
        print("Validation successful.")
        sys.exit(0)
        
    except Exception as e:
        print(f"FAIL: Exception {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
