-- 005 · Entrega 4: de quién es cada cosa. El `sub` de Cognito de quien creó el estudio y el
-- trabajo, y de quien publicó el modelo ('plataforma' para los de la demo, 'anonimo' en local).
-- La API contesta 404 si un estudio o un trabajo es de otro usuario, salvo a un admin de
-- plataforma; y solo quien publicó un modelo le cambia el contrato.
-- Las filas anteriores quedan en null: no son de nadie, y solo las ve un admin.
-- No depende de ninguna otra migración posterior a la 003.

alter table estudio add column if not exists creado_por    text;
alter table trabajo add column if not exists creado_por    text;
alter table modelo  add column if not exists publicado_por text;
