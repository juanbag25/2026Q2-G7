-- 006 · Entrega 4: el tipo de cuenta (institución o publicador) que elige, una sola vez, quien se
-- registró desde «Ingresar» y quedó sin grupo de Cognito (POST /api/cuenta/tipo).
-- El `sub` de Cognito es la clave: de dos elecciones a la vez, una inserta y la otra choca
-- (on conflict do nothing), relee la que quedó y, si es otro tipo, recibe 409. La API agrega el
-- grupo en Cognito después de fijar la fila; los permisos siguen saliendo de los grupos.
-- Las cuentas que se registraron por «crear cuenta» no tienen fila: su grupo lo puso la Lambda.
-- No depende de ninguna otra migración.

create table cuenta (
  sub      text primary key,
  tipo     text not null check (tipo in ('institucion', 'publicador')),
  elegida  timestamptz not null default now()
);
