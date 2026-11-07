#!/usr/bin/env python3
"""Compare two local Skill snapshots with unchanged model and checker settings."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'harness'))
from docforensics.formula_repair import assess_candidate, repair_blocker
from docforensics.skills_runtime import load_skill
from run_local_repair_control import digest, summarize


def policy_metrics(rows):
    selected = [r for r in rows if r['group'] == 'model_with_skill'
                and r['initial_checker']['status'] == 'RETRY']
    attempts = [a for r in selected for a in r['attempts']]
    # Source-policy conformity includes safe deferral; it is not repair yield.
    conformity = sum(a.get('candidate_latex') is not None and
                     assess_candidate(r['original_latex'], a['candidate_latex'])['allowed']
                     for r in selected for a in r['attempts'])
    safe_repairs = [r for r in selected if r['candidate_accepted_by_syntax_checker']
                    and repair_blocker(r['original_latex']) is None
                    and assess_candidate(r['original_latex'], r['output_latex'])['allowed']]
    return {'repair_inputs': len(selected), 'http_attempts': sum(r['model_calls'] for r in selected),
            'strict_candidates': sum(a['provider_trace']['reason'] == 'ok' for a in attempts),
            'candidate_attempts': len(attempts), 'policy_conforming_candidates': conformity,
            'unsafe_changed_candidates': sum(isinstance(a.get('candidate_latex'), str)
                and not assess_candidate(r['original_latex'], a['candidate_latex'])['allowed']
                for r in selected for a in r['attempts']),
            'safe_syntax_repairs': len(safe_repairs),
            'unchanged_deferral_inputs': sum(bool(r['attempts']) and all(
                a.get('candidate_latex') == r['original_latex'] for a in r['attempts']) for r in selected),
            'semantic_accuracy': None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--baseline-root', required=True, type=Path)
    parser.add_argument('--candidate-root', required=True, type=Path)
    parser.add_argument('--outdir', required=True, type=Path)
    parser.add_argument('--repeats', type=int, choices=range(1, 4), default=1)
    args = parser.parse_args()
    if args.base not in ('http://127.0.0.1:18149', 'http://127.0.0.1:18149/v1'):
        parser.error('use the isolated local experiment endpoint on port 18149')
    snapshots = {'baseline': args.baseline_root.resolve(), 'candidate': args.candidate_root.resolve()}
    skills = {name: load_skill(skill_root=root) for name, root in snapshots.items()}
    if skills['baseline'].sha256 == skills['candidate'].sha256:
        parser.error('comparison requires different Skill bodies')
    if skills['baseline'].checker_sha256 != skills['candidate'].checker_sha256:
        parser.error('checker changes confound a Skill-only comparison')
    args.outdir.mkdir(parents=True, exist_ok=False)
    catalogs = ['smoke_cases.json', 'active_calculus_cases.json', 'skill_transfer_cases.json']
    frozen_paths = [ROOT / 'scripts/evaluate_skills.py', ROOT / 'harness/docforensics/vlm.py',
                    Path(__file__).resolve(), ROOT / 'harness/docforensics/formula_repair.py',
                    ROOT / 'harness/docforensics/tex_context.py',
                    *[ROOT / 'samples/research' / name for name in catalogs]]
    frozen = {str(p.relative_to(ROOT)): digest(p) for p in frozen_paths}
    identity = {'status': 'running', 'model': args.model, 'base': args.base,
                'max_tokens': 1024, 'temperature': 0, 'seed': 0, 'response_format': 'text',
                'repeats': args.repeats, 'skill_sha256': {n: s.sha256 for n, s in skills.items()},
                'checker_sha256': skills['baseline'].checker_sha256, 'implementation': frozen,
                'purpose': 'Skill-only source-preservation behavior; no independent semantic review'}
    (args.outdir / 'identity.json').write_text(json.dumps(identity, indent=2))
    summaries = []
    controls = {}
    for repeat in range(args.repeats):
        for catalog in catalogs:
            for name in (('baseline', 'candidate') if repeat % 2 == 0 else ('candidate', 'baseline')):
                for key, root in snapshots.items():
                    if load_skill(skill_root=root).sha256 != skills[key].sha256:
                        raise ValueError('Skill changed during comparison')
                if any(digest(ROOT / p) != sha for p, sha in frozen.items()):
                    raise ValueError('implementation or inputs changed during comparison')
                run = args.outdir / f'{repeat + 1}-{name}-{catalog[:-5]}'
                command = [sys.executable, str(ROOT / 'scripts/evaluate_skills.py'), 'run',
                    '--cases', str(ROOT / 'samples/research' / catalog), '--outdir', str(run),
                    '--mode', 'model', '--base', args.base, '--model', args.model,
                    '--max-tokens', '1024', '--seed', '0', '--skill-root', str(snapshots[name])]
                result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
                (args.outdir / (run.name + '-process.json')).write_text(json.dumps({
                    'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}, indent=2))
                summarize(run)
                if result.returncode:
                    raise ValueError('run failure; evidence preserved, comparison stopped')
                rows = [json.loads(line) for line in (run / 'results.jsonl').read_text().splitlines()]
                # The no-Skill arm must receive byte-identical prompts across snapshots.
                prompt_hashes = [(r['case_id'], [a['provider_trace'].get('prompt_sha256') for a in r['attempts']])
                                 for r in rows if r['group'] == 'model_without_skill']
                key = (repeat, catalog)
                if key in controls and controls[key] != prompt_hashes:
                    raise ValueError('no-Skill prompt control changed')
                controls[key] = prompt_hashes
                summaries.append({'run': run.name, 'snapshot': name, 'catalog': catalog,
                                  'repeat': repeat + 1, 'metrics': policy_metrics(rows)})
                (args.outdir / 'summary.json').write_text(json.dumps(summaries, indent=2))
                print(run.name, summaries[-1]['metrics'], flush=True)
    identity['status'] = 'complete'
    (args.outdir / 'identity.json').write_text(json.dumps(identity, indent=2))


if __name__ == '__main__':
    main()
