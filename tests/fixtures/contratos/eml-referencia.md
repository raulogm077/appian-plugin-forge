# Contrato — Email File Reader (plugin de referencia)

Smart service real, publicado en el AppMarket de Appian y aprobado sin que el
revisor pidiera ningun cambio. Lee documentos Microsoft Outlook MSG y
RFC 5322/MIME EML almacenados en Appian y expone su contenido — remitente,
destinatarios, cuerpo, adjuntos, cabeceras — como salidas del proceso.

Sirve de oraculo de verdad para esta bateria: los valores de abajo estan
leidos directamente de `C:\Users\rgmoya\Documents\Plugin Read EML (Codex)`
(`src/main/resources/appian-plugin.xml`, el bundle
`readEmailFile_en_US.properties` y los setters/getters de
`ReadEmailFileSmartService.java`), no inventados. El `required` de cada
entrada sale de su anotacion `@Input` real; las descripciones son el texto
verbatim de `input.<Name>.comment` / `output.<Name>.comment` en ingles, para
no arriesgar una paraphrasis que se aleje del significado real.

```toml
[plugin]
key = "com.raul.appian.emailfilereader"
nombre = "Email File Reader"
version = "1.0.0"
paquete = "com.raul.appian.emailfilereader"
tipo = "smart-service"
perfil = "riguroso"
application_version_min = "26.6"
descripcion = "Reads Microsoft Outlook MSG and RFC 5322/MIME EML documents from Appian."

[clase]
nombre = "ReadEmailFileSmartService"
paleta = "Document Management"

[bundle]
nombre = "readEmailFile"

[[entradas]]
nombre = "SourceDocument"
tipo_java = "Long"
required = "ALWAYS"
descripcion = "Existing Appian MSG or EML document to process."

[[entradas]]
nombre = "TargetFolder"
tipo_java = "Long"
required = "OPTIONAL"
descripcion = "Appian folder used for extracted attachment documents."

[[entradas]]
nombre = "ExtractAttachments"
tipo_java = "Boolean"
required = "OPTIONAL"
descripcion = "Create an Appian document for every extractable attachment."

[[entradas]]
nombre = "ExtractEmbeddedEmails"
tipo_java = "Boolean"
required = "OPTIONAL"
descripcion = "Process MSG, EML, and message/rfc822 attachments."

[[entradas]]
nombre = "SanitizeHtml"
tipo_java = "Boolean"
required = "OPTIONAL"
descripcion = "Produce a safe HTML representation without executable or tracking content."

[[entradas]]
nombre = "MaxEmbeddedDepth"
tipo_java = "Long"
required = "OPTIONAL"
descripcion = "Maximum number of nested email levels to process."

[[entradas]]
nombre = "MaxFileSizeBytes"
tipo_java = "Long"
required = "OPTIONAL"
descripcion = "Maximum accepted size for the source Appian document."

[[entradas]]
nombre = "MaxAttachmentSizeBytes"
tipo_java = "Long"
required = "OPTIONAL"
descripcion = "Maximum decoded size for one attachment."

[[salidas]]
nombre = "DetectedFormat"
tipo_java = "String"
descripcion = "MSG or EML, determined from the actual document structure."

[[salidas]]
nombre = "Subject"
tipo_java = "String"
descripcion = "Decoded email subject."

[[salidas]]
nombre = "SenderName"
tipo_java = "String"
descripcion = "Display name of the sender when available."

[[salidas]]
nombre = "SenderAddress"
tipo_java = "String"
descripcion = "SMTP or source email address of the sender."

[[salidas]]
nombre = "ReplyTo"
tipo_java = "String"
descripcion = "Comma-separated reply addresses."

[[salidas]]
nombre = "ToRecipients"
tipo_java = "String[]"
descripcion = "Primary recipient addresses."

[[salidas]]
nombre = "CcRecipients"
tipo_java = "String[]"
descripcion = "Carbon-copy recipient addresses."

[[salidas]]
nombre = "BccRecipients"
tipo_java = "String[]"
descripcion = "Blind-carbon-copy addresses when retained in the file."

[[salidas]]
nombre = "SentDateTime"
tipo_java = "Timestamp"
descripcion = "Normalized message sent time when available."

[[salidas]]
nombre = "ReceivedDateTime"
tipo_java = "Timestamp"
descripcion = "Normalized message received time when available."

[[salidas]]
nombre = "MessageId"
tipo_java = "String"
descripcion = "Original RFC message identifier when available."

[[salidas]]
nombre = "BodyText"
tipo_java = "String"
descripcion = "Plain text body or readable text derived from HTML or RTF."

[[salidas]]
nombre = "BodyHtml"
tipo_java = "String"
descripcion = "Original untrusted HTML for traceability; do not render without sanitizing."

[[salidas]]
nombre = "SanitizedBodyHtml"
tipo_java = "String"
descripcion = "HTML stripped of executable and external tracking content."

[[salidas]]
nombre = "HeadersJson"
tipo_java = "String"
descripcion = "JSON array preserving all available headers, including repeated headers."

[[salidas]]
nombre = "EmailDataJson"
tipo_java = "String"
descripcion = "Complete structured result for the root and embedded messages."

[[salidas]]
nombre = "AttachmentDocuments"
tipo_java = "Long[]"
descripcion = "Appian documents created for extracted attachments."

[[salidas]]
nombre = "AttachmentMetadataJson"
tipo_java = "String"
descripcion = "Flat JSON metadata for root and embedded-message attachments."

[[salidas]]
nombre = "WarningMessages"
tipo_java = "String[]"
descripcion = "Non-blocking issues encountered while preserving recoverable data."

[[salidas]]
nombre = "ErrorOccurred"
tipo_java = "Boolean"
descripcion = "Indicates a total processing failure."

[[salidas]]
nombre = "ErrorMessage"
tipo_java = "String"
descripcion = "Safe failure message containing a correlation reference."

[capacidades]
parsea_formatos_ajenos = true
sale_a_la_red = false
toca_credenciales = false
datos_personales = true

[confirmacion]
usuario_confirmo = true
```
