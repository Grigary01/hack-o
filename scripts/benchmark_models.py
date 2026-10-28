"""Сравнение провайдеров на одинаковых данных, промпте и Pydantic-схеме.

По умолчанию только preflight: без генерации и без загрузки весов. --run явно
включает реальные запросы. Нет ключа/модели — статус blocked, НЕТ выдуманных
метрик. Все 44 исходных запроса синтетические, автор — coding assistant; набор
не прошёл независимую человеческую валидацию и не является настоящим gold.
"""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import time
import httpx
from app.core.config import ROOT, settings, MODEL_CONFIG
from app.ml.query_parser import make_parser, ParserError
from app.schemas.query import ParsedHotelQuery
from scripts.evaluate_parser import measure


def preflight(profile, config=settings, client=None):
    if profile['mode']=='groq' and not config.groq_api_key:
        return {'ready':False,'reason':'missing_GROQ_API_KEY'}
    owned=client is None
    client=client or httpx.Client(timeout=15)
    try:
        if profile['mode']=='groq':
            response=client.get('https://api.groq.com/openai/v1/models',
                                headers={'Authorization':'Bearer '+config.groq_api_key})
            response.raise_for_status()
            available=[r['id'] for r in response.json()['data']]
        else:
            response=client.get(config.ollama_url.rstrip('/')+'/api/tags')
            response.raise_for_status()
            records=response.json()['models']
            available=[r['name'] for r in records]
        if profile['model'] not in available:
            return {'ready':False,'reason':'model_not_available_or_not_installed'}
        metadata={'ready':True}
        if profile['mode']=='ollama':
            item=next(r for r in records if r['name']==profile['model'])
            metadata['model_digest']=item.get('digest')
        return metadata
    except (httpx.HTTPError,KeyError,TypeError,ValueError):
        return {'ready':False,'reason':'provider_unavailable'}
    finally:
        if owned: client.close()


def evaluate_cases(profile, rows, parser, interval_seconds=0, checkpoint=None):
    """Сохраняем каждый ответ; failed calls остаются в знаменателе метрик.

Время включает разбор и возможный retry, но не паузы квоты. p95 для маленькой
выборки — только диагностическая величина, не гарантия времени ответа в проде.
"""
    cases=[]
    for index,row in enumerate(rows):
        if index and interval_seconds:
            # Не держим один blocking sleep дольше минуты.
            left=interval_seconds
            while left>0:
                pause=min(left,30)
                time.sleep(pause)
                left-=pause
        start=time.perf_counter()
        try:
            actual=parser.parse(row['text']).model_dump(mode='json')
            error=None
        except ParserError as exc:
            actual=None
            error=str(exc)
        cases.append(dict(text=row['text'],split=row['split'],actual=actual,error=error,
                          latency_seconds=round(time.perf_counter()-start,4)))
        if checkpoint: checkpoint(cases)
        print(f'{profile["id"]}: {index+1}/{len(rows)} {"error" if error else "ok"}',flush=True)

    by_text={c['text']:c for c in cases}
    class Replay:
        def parse(self,text):
            item=by_text[text]
            if item['error']: raise ParserError(item['error'])
            return ParsedHotelQuery.model_validate(item['actual'])
    splits={split:measure([r for r in rows if r['split']==split],Replay())
            for split in sorted({r['split'] for r in rows})}
    times=sorted(c['latency_seconds'] for c in cases)
    return dict(metrics=splits,cases=cases,
                latency_median_seconds=statistics.median(times) if times else None,
                latency_p95_seconds=times[max(0,__import__('math').ceil(.95*len(times))-1)] if times else None,
                errors=sum(c['error'] is not None for c in cases))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profiles',nargs='+',default=['groq-20b','groq-120b','groq-qwen27b'])
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--split',choices=['demo','held_out','all'],default='held_out')
    parser.add_argument('--limit',type=int)
    parser.add_argument('--interval',type=float,default=60,help='Пауза между запросами; бесплатная TPM-квота ограничена')
    parser.add_argument('--output',type=Path,default=ROOT/'runtime/model_comparison.json')
    args=parser.parse_args()
    if args.interval<0 or (args.limit is not None and args.limit<1): parser.error('Некорректные limit/interval')
    profiles=json.loads((ROOT/'data/evaluation/model_candidates.json').read_text())
    known={p['id'] for p in profiles}
    if set(args.profiles)-known: parser.error('Неизвестный профиль')
    dataset=ROOT/'data/evaluation/queries_gold.jsonl'
    rows=[json.loads(line) for line in dataset.read_text().splitlines() if line.strip()]
    rows=[r for r in rows if args.split=='all' or r['split']==args.split]
    if args.limit: rows=rows[:args.limit]
    report=dict(created_at=datetime.now(timezone.utc).isoformat(),generation_enabled=args.run,
                model_config=MODEL_CONFIG.model_dump(),
                model_config_sha256=hashlib.sha256((ROOT/'config/models.yaml').read_bytes()).hexdigest(),
                dataset_sha256=hashlib.sha256(dataset.read_bytes()).hexdigest(),
                prompt_sha256=hashlib.sha256((ROOT/'app/ml/prompts.py').read_bytes()).hexdigest(),
                schema_sha256=hashlib.sha256(json.dumps(ParsedHotelQuery.model_json_schema(),sort_keys=True).encode()).hexdigest(),
                note='Synthetic assistant-authored labels; human review required. No model quality measured in preflight.',
                split=args.split,queries=len(rows),profiles=[])
    def save():
        args.output.parent.mkdir(parents=True,exist_ok=True)
        temp=args.output.with_suffix('.tmp')
        temp.write_text(json.dumps(report,ensure_ascii=False,indent=2))
        temp.replace(args.output)
    for profile in profiles:
        if profile['id'] not in args.profiles: continue
        config=replace(settings,parser_mode=profile['mode'],model_name=profile['model'],groq_model=profile['model'])
        check=preflight(profile,config)
        item=dict(profile,preflight=check,status='ready' if check['ready'] else 'blocked')
        report['profiles'].append(item)
        save()
        if args.run and check['ready']:
            model=make_parser(config)
            item['status']='running'
            def checkpoint(cases):
                item['cases']=list(cases)
                save()
            try:
                item.update(evaluate_cases(profile,rows,model,args.interval,checkpoint))
                item['status']='measured'
            finally:
                model.client.close()
                save()
        print(profile['id'],item['status'],flush=True)
    print(args.output)


if __name__=='__main__':
    main()
