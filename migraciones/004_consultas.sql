-- 004 · la junta de modelos (spec funcional F8): una consulta agrupa los trabajos de varios
-- modelos sobre el mismo estudio, uno por modelo. Ni el estado de la consulta ni el informe de
-- consenso se guardan: se calculan al leer, con los trabajos y las métricas verificadas.
-- Un trabajo sin consulta es una consulta individual, como hasta ahora.

create table consulta (
  id          uuid primary key default gen_random_uuid(),
  estudio_id  uuid not null references estudio(id),
  creada      timestamptz not null default now()
);

alter table trabajo add column consulta_id uuid references consulta(id);
create index trabajo_por_consulta on trabajo (consulta_id) where consulta_id is not null;
