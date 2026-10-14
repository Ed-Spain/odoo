# Addons Odoo ITP Piscinas

Módulos propios y mantenidos para la instalación de Odoo 18 Community de Innovación Técnica Piscinas S.L.

## itp_product_multi_image

Port a Odoo 18 del módulo comunitario `product_multi_image`. Añade una galería de imágenes a las plantillas y variantes de producto.

Dependencias: `base_multi_image` de OCA (`server-tools`, rama 18.0).

Instalar primero en la base de pruebas, actualizar la lista de aplicaciones e instalar `ITP Product Multi Image`.

El código conserva los avisos de atribución y la licencia AGPL-3.0 del proyecto de origen.
## fleet_traccar

Conector LGPL-3 para enlazar la aplicación Flota con un servidor [Traccar](https://www.traccar.org/). Importa dispositivos y última posición, permite asociarlos a vehículos y sincroniza opcionalmente el odómetro calibrado.

Dependencia: la aplicación estándar `fleet` y el paquete Python `requests`. Configura la URL y credenciales de Traccar dentro de Odoo; el código publicado no incluye configuraciones ni credenciales.
