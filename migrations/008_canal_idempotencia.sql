-- Un reenvío del proveedor no se procesa dos veces: el identificador externo es único por negocio y canal.
create unique index mensaje_id_externo_neg on mensaje(negocio_id, canal, id_externo) where id_externo is not null;
