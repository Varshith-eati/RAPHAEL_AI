"""Grounded reports for facts/actions that do not need model paraphrasing."""
def hardware_report(info):
    lines = ['Here are the details read from your laptop:']
    for key, label in [('cpu', 'Processor'), ('ram_gb', 'RAM'), ('logical_processors', 'Logical processors'),
                       ('model', 'Laptop model'), ('operating_system', 'System')]:
        if info.get(key) is not None:
            value = str(info[key])+(' GB' if key=='ram_gb' else '')
            lines.append(label+': '+value)
    if info.get('graphics'):
        lines.append('Graphics: '+', '.join(info['graphics']))
    if info.get('workspace_disk'):
        disk=info['workspace_disk']
        lines.append(f"Workspace drive: {disk['free_gb']} GB free of {disk['total_gb']} GB")
    return '\n'.join(lines)
