"""Render the data-package README from the independently reconstructed UTC counts and weights."""
import csv
import io

from common import FEATURES, SOURCE_COMMIT, utc


def render(tables, slots, counts, inputs):
    def records(name):
        return csv.DictReader(io.StringIO(tables[name + '.csv'].decode()))

    metrics = {(r['window'], r['arm'], r['metric']): r for r in records('metric-counts')}
    days = {(r['window'], r['seat']): r for r in records('day-counts') if r['scope'] == 'all'}
    weights = {(r['phase'], r['arm'], r['feature']): r for r in records('weights')}
    windows = [('evaluation', '2025 测试'), ('recent', '2026/27 近期')]
    complete = sum(f['both_complete'] for f in counts['folds'].values())
    snapshot = utc(inputs['roster_snapshot_at']).isoformat().replace('+00:00', 'Z')
    lines = [
        '# R15 日本 J1 历史首发数据', '',
        f"快照截止 {snapshot}。原 R5 日历共 {counts['fixture_slots']:,} 场，"
        f"采集快照含 {counts['training_rows']:,} 行，{complete:,} 场的双方名单通过 R15 首发资格核验。"
        '特征只取严格更早比赛日的名单与残差。', '',
        '## 历史回放', '',
    ]
    for window, label in windows:
        dates = [s['date'] for s in slots if s['fold'] == window]
        lines.append(f'{label}窗为 {min(dates)} 至 {max(dates)}，固定 {len(dates)} 场。')
    lines.extend(['日期取原 ESPN 开球时刻的 UTC 日。分数为命中数/可结算场数，横线表示可结算场数为零。', '',
                  '| UTC 窗口 | 指标 | R15 六列 | 仅球队状态 | R5 | R7 | R10 | 市场 |',
                  '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |'])
    for window, label in windows:
        for key, title in [('score_top1','首选比分'), ('score_top3','前三比分'), ('wdl','胜平负'), ('actual_ou','实际盘大小球')]:
            cells = [label, title]
            for arm in ('candidate', 'form_only', 'r5', 'r7', 'r10', 'market'):
                r = metrics[window, arm, key]
                cells.append(f"{r['hits']}/{r['eligible']}" if int(r['eligible']) else '—')
            lines.append('| ' + ' | '.join(cells) + ' |')
    lines.extend(['', '每日按首选比分概率降序、赛事 ID 升序取前三席。席位列为首选命中/前三命中/入选场数。', '',
                  '| UTC 窗口 | 比赛日 | 满三场/短日 | 席一 | 席二 | 席三 | 三席首选全中/满三场日 |',
                  '| --- | ---: | ---: | ---: | ---: | ---: | ---: |'])
    for window, label in windows:
        r = days[window, 'all']
        seats = [days[window, str(i)] for i in (1, 2, 3)]
        cells = [label, r['days'], f"{r['full_days']}/{r['short_days']}",
                 *(f"{s['first_hits']}/{s['ordered_three_hits']}/{s['selected']}" for s in seats),
                 f"{r['sweeps']}/{r['full_days']}"]
        lines.append('| ' + ' | '.join(cells) + ' |')
    lines.extend(['', '## 拟合权重', '',
                  '每格依次为进球概率系数与条件正进球数系数，显示八位有效数字。两列模型使用前两项特征。', '',
                  '| 特征 | 初训六列 | 初训两列 | 全历史六列 | 全历史两列 |',
                  '| --- | ---: | ---: | ---: | ---: |'])
    for feature in FEATURES:
        cells = [f'`{feature}`']
        for phase, arm in [('train','full'), ('train','form'), ('forward','full'), ('forward','form')]:
            r = weights.get((phase, arm, feature))
            cells.append(f"{float(r['scoring_beta']):.8g} / {float(r['positive_beta']):.8g}" if r else '—')
        lines.append('| ' + ' | '.join(cells) + ' |')
    lines.append('')
    for arm, label in [('full','六列模型'), ('form','两列模型')]:
        t, f = (weights[phase, arm, FEATURES[0]] for phase in ('train', 'forward'))
        lines.append(f"{label}的初训和全历史拟合分别使用 {t['fit_games']}/{t['training_games']}、"
                     f"{f['fit_games']}/{f['training_games']} 场。验证期选出的比分/胜平负/大小球剂量为 "
                     f"{t['score_dose']}/{t['wdl_dose']}/{t['total_dose']}。")
    lines.extend(['', f'源码 `{SOURCE_COMMIT}`。回顾性结果按预登记窗口统计。',
                  '[指标](metric-counts.csv) · [日批次](day-counts.csv) · [成对比较](paired-counts.csv) · '
                  '[完整精度权重](weights.csv) · [复算命令与证据结构](VERIFYING.md)', ''])
    return '\n'.join(lines).encode()
