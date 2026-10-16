// Home's share of Create (the Create page lives under Home now): a compact "Start from" row under the composer (the
// formats, write a script, record yourself - each opens Create's own screen) and "Keep creating" (her series in
// progress). Both only with the Create flag on; what they last loaded is shown at once on the next visit (no flash).
import { useEffect, useRef } from 'react';
import { BookOpen, Circle, PenLine } from 'lucide-react';
import type { Format, SeriesSummary } from '../../../shared/create';
import { t } from '../i18n';
import { useCreate, useCreateLoad, msgText } from '../create/api';
import { FormatArt, l10n } from '../create/bits';
import { useCreateEnabled } from '../create/flag';
import { createHref } from '../create/routes';
import { media } from './kit';
import '../create/create.css';

const cache: { formats: Format[] | null; series: SeriesSummary[] | null } = { formats: null, series: null };

function statusClass(code?: string): string {
  if (!code) return '';
  if (code.endsWith('.pick') || code.endsWith('.you')) return 'you';
  if (code.endsWith('.making') || code.endsWith('.board')) return 'run';
  if (code.endsWith('.ready') || code.endsWith('.assemble')) return 'ok';
  return '';
}

/** The starts: a format plans a new series of it, "Write a script" plans one with the format left to AI, "Record"
 * opens the teleprompter. ``scrollTo``: #/create landed here - bring the row into view. */
export function HomeStartFrom({ scrollTo }: { scrollTo?: boolean }) {
  const on = useCreateEnabled();
  return on ? <StartRow scrollTo={scrollTo} /> : null;
}

function StartRow({ scrollTo }: { scrollTo?: boolean }) {
  const c = useCreate();
  const { data } = useCreateLoad((x) => x.formats(), []);
  if (data) cache.formats = data.formats;
  const fmts = (data?.formats ?? cache.formats ?? []).filter((f) => f.id !== 'record');
  const box = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (scrollTo) box.current?.scrollIntoView({ block: 'center' });
  }, [scrollTo]);
  // a recording that survived an app quit: hand it to the engine once (it remuxes, the inbox says so)
  useEffect(() => {
    if (!c) return;
    void window.desk.rec
      ?.recover()
      .then((rows) => (rows.length ? c.recover() : null))
      .catch(() => undefined);
  }, [c]);
  return (
    <section className="ux-startfrom" ref={box} data-testid="home-start-from">
      <span className="lbl">{t('create.start.title')}</span>
      <a className="ux-sf" href={createHref({ screen: 'learning' })} data-tip={t('learning.flow')} data-testid="home-create-learning">
        <BookOpen className="ico" />{t('learning.creation')}
      </a>
      {fmts.map((f) => (
        <a key={f.id} className="ux-sf" href={createHref({ screen: 'new', format: f.id })} data-tip={l10n(f.blurb)} data-testid={`create-fmt-${f.id}`}>
          <span className="art">
            <FormatArt id={f.id} badge={false} />
          </span>
          {l10n(f.labels)}
        </a>
      ))}
      <a className="ux-sf" href={createHref({ screen: 'new' })} data-tip={t('create.start.scriptTip')} data-testid="home-start-script">
        <PenLine className="ico" />
        {t('create.start.script')}
      </a>
      <a className="ux-sf" href={createHref({ screen: 'record' })} data-tip={t('create.start.recordTip')} data-testid="home-start-record">
        <Circle className="ico rec" />
        {t('st.record')}
      </a>
    </section>
  );
}

/** Her series in progress (scripts, episodes being made): a compact list, only when there are any. */
export function HomeKeepCreating() {
  const on = useCreateEnabled();
  return on ? <KeepCreating /> : null;
}

function KeepCreating() {
  const { data: s } = useCreateLoad((x) => x.listSeries(), []);
  const { data: f } = useCreateLoad((x) => x.formats(), []);
  if (s) cache.series = s.series;
  if (f) cache.formats = f.formats;
  const rows = s?.series ?? cache.series ?? [];
  const fmts = f?.formats ?? cache.formats ?? [];
  if (!rows.length) return null;
  return (
    <section className="ux-sec" data-testid="home-keep-creating">
      <div className="ux-sech">
        <h2>{t('create.continue.title')}</h2>
        <span className="muted">{rows.length}</span>
      </div>
      <div className="card ux-hlist">
        {rows.slice(0, 6).map((x) => {
          const fm = fmts.find((y) => y.id === x.format);
          const fname = fm ? l10n(fm.labels) : x.format;
          return (
            <div key={x.id} className="ux-hrow">
              <a className="ux-hrow-main" href={createHref({ screen: 'series', sid: x.id, tab: 'bible' })} data-testid="create-series-card">
                <span className="ux-sfcv">{x.cover ? <img src={media(x.cover)} alt="" /> : <FormatArt id={x.format} badge={false} />}</span>
                <span className="tx">
                  <b className="clamp1">{x.name}</b>
                  <span className="muted clamp1">
                    {x.last ? (x.planned ? t('create.series.epOf', { format: fname, n: x.last, total: x.planned }) : t('create.series.ep', { format: fname, n: x.last })) : t('create.series.noEp', { format: fname })}
                  </span>
                </span>
              </a>
              {x.status && <span className={`cr-pill ${statusClass(x.status.code)}`}>{msgText(x.status)}</span>}
            </div>
          );
        })}
      </div>
    </section>
  );
}
