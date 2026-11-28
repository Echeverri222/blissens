"""Textos del sitio público (landing) en español e inglés. Diccionarios simples, sin librería de i18n.

El español es la versión por defecto. El inglés sale de https://blissens.com/; el español del sitio real se traduce en el
navegador (Weglot), así que estos textos están redactados a partir del original en inglés."""
from urllib.parse import quote, quote_plus

HORARIO = {"es": "Lunes a viernes 8 a. m. a 5 p. m. · Sábados 8 a. m. a 12 m.",
           "en": "Monday to Friday 8 a.m. to 5 p.m. · Saturday 8 a.m. to 12 p.m."}
DIRECCION = ("Carrera 25 # 1A Sur 45, C.C. El Tesoro, Torre Médica 2, consultorios 1156 y 1157, El Poblado, Medellín, "
             "Colombia")
MAPA = "https://www.google.com/maps/search/?api=1&query=" + quote_plus(DIRECCION)
CORREO = "info@blissens.com"
TELEFONO = "+57 305 306 9616"
TELEFONO_TEL = "+573053069616"
# El sitio real muestra los íconos de Instagram y Facebook sin enlace; aquí se dejan sin enlace hasta tener la dirección.
TEXTO_WHATSAPP = {"es": "Hola, vengo del sitio web y quiero agendar una valoración",
                  "en": "Hola, vengo del sitio web y quiero agendar una valoración"}


def enlace_whatsapp(numero, lang="es"):
    """Enlace wa.me con texto prellenado, o None si no hay número configurado (entonces no se muestra nada)."""
    digitos = "".join(c for c in str(numero or "") if c.isdigit())
    return f"https://wa.me/{digitos}?text={quote(TEXTO_WHATSAPP[lang])}" if digitos else None


REDES = {"Instagram": None, "Facebook": None}

IMAGENES = {"equipo": "New-Team.jpg", "confort": "BLISSENSE-1.png", "servicios": "Services.jpg"}

# Interés → etiqueta (en español, para quien lee la bandeja del panel) de las solicitudes que llegan del sitio.
INTERESES = {"evaluacion_virtual": "Evaluación virtual", "experiencia": "Experiencia", "contacto": "Contacto"}
PAQUETES = {"premium": "Premium (hotel)", "standard": "Standard (Airbnb)", "essential": "Essential (transporte)"}

ES = {
    "lang": "es", "otro_idioma": "en", "otro_idioma_nombre": "EN", "idioma_nombre": "ES",
    "home": "/", "otro_home": "/en",
    "agendar_url": "/agendar",  # página aparte, sin distracciones; con JavaScript el botón abre el asistente
    "evaluacion_url": "/evaluacion", "contacto_url": "/contacto", "experiencia_url": "/experiencia?idioma=es",
    "pag_agendar": {"kicker": "Blissens Odontología · Medellín", "titulo": "Agende su cita",
                    "lead": "Toma menos de un minuto. Sin cuentas ni contraseñas: solo su documento y su celular.",
                    "pasos": ["Identifíquese", "Elija el día y la hora", "Reciba la confirmación por WhatsApp"],
                    "paso1": "Paso 1 de 3 · Identifíquese", "volver": "Volver al sitio",
                    "info": "Dónde y cuándo atendemos", "donde": "Dónde", "horario": "Horario",
                    "ayuda": "¿Prefiere que le ayudemos? Llámenos o escríbanos por WhatsApp"},
    "meta": {"titulo": "Blissens · Estudio odontológico de alta tecnología en Medellín",
             "descripcion": "Odontología digital y diseño de sonrisa en Medellín. Agende su cita o reciba una evaluación "
                            "virtual si vive en el exterior.",
             "og_locale": "es_CO"},
    "saltar": "Saltar al contenido",
    "nav_aria": "Principal", "nav": [("nosotros", "Nosotros"), ("servicios", "Servicios"),
                                      ("antes-despues", "Antes y después"),
                                      ("evaluacion", "Evaluación virtual"), ("experiencias", "Experiencias"),
                                      ("contacto", "Contacto")],
    "menu_abrir": "Abrir menú", "menu_cerrar": "Cerrar menú",
    "cta": "Agendar cita", "ingresar": "Ingresar",
    "hero": {"kicker": "Tu futura sonrisa", "titulo": ["Sonría y mire", "al futuro"],
             "sub": ["Odontología digital", "Estudio odontológico de alta tecnología"],
             "afuera": "Vivo en el exterior", "local": "Vivo en Medellín", "aria": "Elija cómo quiere empezar"},
    "adn": {"kicker": "Nuestro ADN", "titulo": "Conectando con la sonrisa del alma",
            "texto": "Bienvenido a Blissens®. Este es un espacio de encuentro humano que une la experticia digital con "
                     "técnicas estéticas para ofrecer a los pacientes una experiencia emocional de calidad, segura y "
                     "cercana.",
            "marquee": ["Estudio odontológico de alta tecnología", "Blissens", "Sonría y mire al futuro"]},
    "emocion": {"titulo": "Rehabilitamos a través de la emoción",
                "texto": "Somos especialistas en rehabilitación oral, egresados de la Universidad CES de Medellín. "
                         "JuanMa, con maestría clínica en odontología digital, le transmitió esa pasión a Sara, y hoy "
                         "trabajan exclusivamente con esta filosofía en Blissens®. Nos sumergimos en la experiencia con "
                         "nuestros pacientes para personalizar cada tratamiento y crear sonrisas únicas.",
                "alt": "Sara López y Juan Manuel Olarte, especialistas en rehabilitación oral"},
    "confort": {"titulo": "Comodidad de principio a fin", "pasos": ["Preludio de la sonrisa", "Diagnóstico",
                                                                   "Procedimiento especializado"],
                "texto": "Viva en Medellín o llegue de viaje, coordinamos todo: tiempos claros, vistas previas "
                         "digitales y procedimientos suaves y precisos. Nos enfocamos en su comodidad en cada etapa para "
                         "que su tratamiento sea simple, transparente y hermosamente predecible."},
    "servicios": {"kicker": "Servicios", "titulo": "Diseño de sonrisa",
                  "texto": "Diseños naturales, pensados para su rostro y creados con maquetas digitales para que vea su "
                           "nueva sonrisa antes de empezar el tratamiento. Ideales para cerrar espacios, corregir forma "
                           "y tamaño y renovar bordes desgastados.",
                  "alt": "Diseño de sonrisa y odontología digital en Blissens Medellín", "ver_mas": "Ver todos los servicios",
                  "lista": [("Diseño de sonrisa", "Diseño digital de sonrisa para anticipar el resultado del tratamiento."),
                            ("Cirugía oral", "Procedimientos quirúrgicos orales con planificación digital."),
                            ("Implantes dentales y cirugía plástica periodontal",
                             "Reposición de dientes y mejora del contorno de las encías."),
                            ("Ortodoncia (fija e invisible)", "Alineación dental con aparatología fija o invisible."),
                            ("Endodoncia", "Tratamiento de conducto para conservar su diente."),
                            ("Rehabilitación oral",
                             "Restauración de dientes perdidos o dañados parcial o totalmente para recuperar función y "
                             "estética. Diseño digital de sonrisa para predecir el tratamiento.")]},
    "evaluacion": {"kicker": "Evaluación virtual", "titulo": "Evaluación virtual",
                   "texto": "En este espacio, las personas que viven en el exterior pueden recibir asesoría "
                            "personalizada. Solo siga los pasos.",
                   "pasos": ["Consulta virtual gratuita", "Complete y envíe el formulario", "Analizamos su caso",
                             "Recibe asesoría virtual especializada"],
                   "form_titulo": "Solicite su evaluación", "boton": "Solicitar evaluación"},
    "antes": {"titulo": "Antes y después",
              "texto": "La consecuencia de nuestro trabajo será mejores expresiones, autoestima y calidad de vida.",
              "antes": "Antes", "despues": "Después", "ejemplo": "Imagen de ejemplo",
              "slider": "Comparar antes y después. Use las flechas del teclado para mover el control.",
              "casos": [("Caso 1", "Trauma dental",
                         "Miles de personas han sufrido golpes y traumas en sus dientes desde niños. Estas situaciones "
                         "no solo implican molestias físicas, sino también emocionales: un cúmulo de emociones."),
                        ("Caso 2", "Diseño de sonrisa", "Forma, tamaño y color armonizados con el rostro."),
                        ("Caso 3", "Rehabilitación oral", "Función y estética recuperadas.")],
              "nota": "Imágenes de ejemplo. Los casos reales se muestran con autorización de cada paciente."},
    "experiencias": {"kicker": "Experiencias", "titulo": "Experiencias",
                     "texto": "Haga que su viaje de sonrisa sea sencillo. Coordinamos estadías, traslados y agenda "
                              "alrededor de su tratamiento para que descanse más, se mueva menos y disfrute Medellín "
                              "mientras nos ocupamos de cada detalle.",
                     "paquetes": [("premium", "Premium", "Hotel", "Primium-460x460.png"),
                                  ("standard", "Standard", "Airbnb", "Standerd-460x460.png"),
                                  ("essential", "Essential", "Transporte", "Basic-460x460.png")],
                     "elegir": "Elegir este paquete", "form_titulo": "Reserve su experiencia",
                     "ok": "Nos emociona ser parte de su viaje. Pronto recibirá un correo con su confirmación y pasos "
                           "sencillos para agendar su visita."},
    "equipo": {"titulo": "Nuestro equipo",
               "personas": [("Sara López", "Rehabilitación oral y diseño de sonrisa", "image-8.png", 248, 373),
                            ("Juan Manuel Olarte", "Rehabilitación oral y diseño de sonrisa", "image-9.png", 250, 374)]},
    "agendar": {"kicker": "En Medellín", "titulo": "Agende su cita",
                "texto": "Si está en Medellín, agende su cita en nuestro consultorio, en la torre médica del centro "
                         "comercial El Tesoro. Sin cuentas ni instalaciones: solo necesitamos su documento y su celular.",
                "boton": "Agendar"},
    "contacto": {"kicker": "Contacto", "titulo": "Contáctenos",
                 "texto": "¿Tiene más preguntas o quiere más asesoría? Escríbanos.",
                 "horario": "Horario", "direccion": "Dirección", "correo": "Correo", "telefono": "Teléfono",
                 "whatsapp": "WhatsApp", "whatsapp_escribir": "Escríbanos por WhatsApp", "mapa": "Ver en el mapa"},
    "form": {"nombre": "Nombre", "correo": "Correo electrónico", "celular": "Celular o WhatsApp", "pais": "País de residencia",
             "paquete": "Paquete", "paquete_ph": "Elija un paquete", "mensaje": "Mensaje", "enviar": "Enviar",
             "consent": "Autorizo el tratamiento de mis datos personales.",
             "ok": "Gracias. Recibimos su solicitud y le responderemos en las próximas {horas} horas.",
             "ok_correo": "Le enviamos una confirmación a su correo.",
             "fotos": "Fotos de su sonrisa o radiografías (opcional)",
             "fotos_ayuda": "Hasta 4 archivos JPG, PNG, WEBP o PDF, de máximo 5 MB cada uno.",
             "err_adjunto_cantidad": "Puede adjuntar hasta 4 archivos.",
             "err_adjunto_tamano": "Cada archivo puede pesar máximo 5 MB (12 MB en total).",
             "err_adjunto_tipo": "Solo aceptamos fotos JPG, PNG o WEBP y documentos PDF.",
             "err_nombre": "Escriba su nombre.", "err_contacto": "Déjenos un correo válido o un celular para responderle.",
             "err_consent": "Para enviar necesitamos su autorización para tratar sus datos.",
             "err_paquete": "Elija un paquete.", "enviando": "Enviando…",
             "err_limite": "Recibimos varias solicitudes desde su conexión. Espere unos minutos e inténtelo de nuevo, o "
                           "escríbanos por WhatsApp."},
    "ident": {"titulo": "Su documento y su celular", "documento": "Documento de identidad", "celular": "Celular",
              "continuar": "Continuar", "primera": "Parece que es su primera vez.",
              "primera2": "Cuéntenos su nombre para registrarlo.", "nombres": "Nombres", "apellidos": "Apellidos",
              "correo": "Correo electrónico (opcional)",
              "acepta_correo": "Quiero recibir por correo la confirmación, el recordatorio y los avisos de cancelación "
                               "de mis citas.",
              "registrar": "Registrarme y continuar", "cargando": "Un momento…",
              "ph_celular": "3001234567", "ph_correo": "usted@correo.com",
              "err_datos": "Revise su documento y su celular (10 dígitos, empieza por 3).",
              "err_consent": "Para registrarse necesitamos su autorización para tratar sus datos.",
              "err_correo": "Escriba un correo válido, o desmarque la opción de recibir correos.",
              "consent": None,  # en español se usa el texto configurado del negocio (`texto_consentimiento`)
              "sin_auto": "No pudimos continuar de forma automática. {termino} se pondrá en contacto con usted muy pronto "
                          "para ayudarle a agendar.",
              "volver": "Volver", "gracias": "Gracias",
              "familia": "¿Va a agendar para sus hijos u otros familiares? Regístrese usted primero y agréguelos desde "
                         "Mis citas."},
    "pie": {"horario": "Horario", "direccion": "Dirección", "contacto": "Contacto", "derechos": "Todos los derechos reservados.",
            "politica": "Política de tratamiento de datos", "equipo": "Acceso equipo", "inicio": "Ir al inicio", "siguenos": "Síguenos"},
    "asistente": {"titulo": "Asistente de citas", "aria": "Bliss, asistente del sitio", "abrir": "Abrir o cerrar a Bliss",
                  "saludo": "Hola, soy {nombre}. Puedo ayudarle con sus citas, horarios y la dirección de la clínica.",
                  "opciones": [("agendar", "Agendar una cita"), ("afuera", "Vivo fuera de Colombia"),
                               ("direccion", "Dirección y horario"), ("otra", "Otra pregunta")],
                  "ya_paciente": "¿Ya es paciente? Use el mismo formulario.",
                  "afuera": "Si vive fuera de Colombia, empezamos con una evaluación virtual: cuéntenos su caso y recibe "
                            "asesoría especializada.",
                  "experiencia": "Elija su paquete y déjenos sus datos: le escribimos para coordinar su viaje.",
                  "direccion": "Atendemos en:", "mapa": "Ver en el mapa", "volver": "Volver",
                  "otra": "Escriba su pregunta y con gusto le ayudo.", "otra_sin": "Déjenos su mensaje y la clínica le responde.",
                  "aviso_ia": "Soy una asistente automática, con inteligencia artificial, y puedo equivocarme. No escriba datos "
                              "personales ni de salud: eso va solo en los formularios.",
                  "texto": "Su pregunta", "enviar": "Enviar", "escribiendo": "Escribiendo…",
                  "err_texto": "Escriba un mensaje de hasta {max} caracteres."},
    "barra": "Agendar cita", "idioma_aria": "Cambiar idioma a inglés",
}

EN = {
    "lang": "en", "otro_idioma": "es", "otro_idioma_nombre": "ES", "idioma_nombre": "EN",
    "home": "/en", "otro_home": "/",
    "agendar_url": "/agendar?idioma=en",  # sin JavaScript, páginas aparte; con él los botones abren el asistente
    "evaluacion_url": "/evaluacion?idioma=en", "contacto_url": "/contacto?idioma=en", "experiencia_url": "/experiencia?idioma=en",
    "pag_agendar": {"kicker": "Blissens Dentistry · Medellín", "titulo": "Book your appointment",
                    "lead": "It takes less than a minute. No accounts or passwords: just your ID number and your phone.",
                    "pasos": ["Identify yourself", "Pick the day and time", "Get the confirmation on WhatsApp"],
                    "paso1": "Step 1 of 3 · Identify yourself", "volver": "Back to the site",
                    "info": "Where and when we see patients", "donde": "Where", "horario": "Hours",
                    "ayuda": "Prefer a hand? Call us or message us on WhatsApp"},
    "meta": {"titulo": "Blissens · High-technology dental studio in Medellín",
             "descripcion": "Digital dentistry and smile design in Medellín. Book an appointment or get a virtual "
                            "assessment if you live abroad.",
             "og_locale": "en_US"},
    "saltar": "Skip to content",
    "nav_aria": "Main", "nav": [("nosotros", "About us"), ("servicios", "Services"), ("antes-despues", "Before - After"),
                                ("evaluacion", "Virtual assessment"),
                                ("experiencias", "Experiences"), ("contacto", "Contact")],
    "menu_abrir": "Open menu", "menu_cerrar": "Close menu",
    "cta": "Book appointment", "ingresar": "Sign in",
    "hero": {"kicker": "Your future smile", "titulo": ["Smile and look", "at the future"],
             "sub": ["Digital dentistry", "High technology & dental studio"],
             "afuera": "I live abroad", "local": "I live in Medellín", "aria": "Choose how you want to start"},
    "adn": {"kicker": "Our DNA", "titulo": "Connecting with the smile of the soul",
            "texto": "Welcome to Blissens®. This is a space for human encounter, blending digital expertise with aesthetic "
                     "techniques to provide patients with a quality, safe, and caring emotional experience.",
            "marquee": ["High technology dental studio", "Blissens", "Smile and look at the future"]},
    "emocion": {"titulo": "We rehabilitate through emotion",
                "texto": "Oral rehabilitation specialists, graduates of CES University in Medellín. JuanMa, with a clinical "
                         "master’s degree in digital dentistry, passed on this passion to Sara, and today they work "
                         "exclusively with this philosophy at Blissens®. We immerse ourselves in the experience with our "
                         "patients to personalize all treatments, creating unique smiles.",
                "alt": "Sara López and Juan Manuel Olarte, oral rehabilitation specialists"},
    "confort": {"titulo": "Comfort from start to finish", "pasos": ["Smile prelude", "Diagnosis", "Specialized procedure"],
                "texto": "Whether you live in Medellín or are flying in, we coordinate everything—clear timelines, digital "
                         "previews, and gentle, precise procedures. Our focus is your comfort at every stage, so your "
                         "treatment feels simple, transparent, and beautifully predictable."},
    "servicios": {"kicker": "Services", "titulo": "Smile design",
                  "texto": "Natural, face-driven designs created with digital mock-ups so you preview your new smile "
                           "before treatment begins. Ideal for closing gaps, correcting shape/size, and refreshing worn "
                           "edges.",
                  "alt": "Digital smile design and dental care at Blissens Medellín", "ver_mas": "See all services",
                  "lista": [("Smile design", "Digital smile design to preview the result of your treatment."),
                            ("Oral surgery", "Oral surgical procedures with digital planning."),
                            ("Dental implants and periodontal plastic surgery",
                             "Tooth replacement and gum contour improvement."),
                            ("Orthodontics (fixed and invisible)", "Teeth alignment with fixed or invisible appliances."),
                            ("Endodontics", "Root canal treatment to keep your tooth."),
                            ("Oral rehabilitation",
                             "Restoration of missing or partially or completely damaged teeth to restore function and "
                             "aesthetics. Digital smile design for treatment prediction.")]},
    "evaluacion": {"kicker": "Virtual assessment", "titulo": "Virtual assessment",
                   "texto": "In this space, people living abroad can receive personalized advice. Just follow the steps "
                            "below.",
                   "pasos": ["Free virtual consultation", "Complete and submit the form", "We analyze your case",
                             "You receive specialized virtual advice"],
                   "form_titulo": "Request your assessment", "boton": "Request assessment"},
    "antes": {"titulo": "Before - After",
              "texto": "The consequence of our work will be improved expressions, self-esteem, and quality of life.",
              "antes": "Before", "despues": "After", "ejemplo": "Sample image",
              "slider": "Compare before and after. Use the keyboard arrow keys to move the handle.",
              "casos": [("Case 1", "Dental trauma",
                         "Thousands of people have suffered trauma and blows to their teeth as children. These situations "
                         "not only involve physical and physiological discomfort, but also emotional discomfort, making "
                         "these scenarios a mixture of emotions."),
                        ("Case 2", "Smile design", "Shape, size and color in harmony with the face."),
                        ("Case 3", "Oral rehabilitation", "Function and aesthetics restored.")],
              "nota": "Sample images. Real cases are shown with each patient’s consent."},
    "experiencias": {"kicker": "Experiences", "titulo": "Experiences",
                     "texto": "Make your smile trip effortless. We coordinate stays, transfers, and scheduling around your "
                              "treatment—so you rest more, move less, and enjoy Medellín while we take care of every "
                              "detail.",
                     "paquetes": [("premium", "Premium", "Hotel", "Primium-460x460.png"),
                                  ("standard", "Standard", "Airbnb", "Standerd-460x460.png"),
                                  ("essential", "Essential", "Transport", "Basic-460x460.png")],
                     "elegir": "Choose this package", "form_titulo": "Book your experience",
                     "ok": "We’re excited to be part of your journey. You’ll soon receive an email with your confirmation "
                           "and easy steps to schedule your visit."},
    "equipo": {"titulo": "Our team",
               "personas": [("Sara López", "Oral rehabilitation and smile design", "image-8.png", 248, 373),
                            ("Juan Manuel Olarte", "Oral rehabilitation and smile design", "image-9.png", 250, 374)]},
    "agendar": {"kicker": "In Medellín", "titulo": "Schedule an appointment",
                "texto": "If you’re in Medellín, schedule an appointment at our office, in the medical tower of the El "
                         "Tesoro shopping center. No accounts or installs: we only need your ID number and your mobile "
                         "phone.",
                "boton": "Book now"},
    "contacto": {"kicker": "Contact", "titulo": "Contact us",
                 "texto": "Have more questions or want more advice? Feel free to contact us.",
                 "horario": "Hours", "direccion": "Address", "correo": "E-mail", "telefono": "Phone",
                 "whatsapp": "WhatsApp", "whatsapp_escribir": "Message us on WhatsApp", "mapa": "View on the map"},
    "form": {"nombre": "Name", "correo": "Email", "celular": "Phone or WhatsApp", "pais": "Country of residence",
             "paquete": "Package", "paquete_ph": "Please select a package", "mensaje": "Message", "enviar": "Send",
             "consent": "I authorize the processing of my personal data.",
             "ok": "Thank you. We received your request and will reply within {horas} hours.",
             "ok_correo": "We sent a confirmation to your email.",
             "fotos": "Photos of your smile or X-rays (optional)",
             "fotos_ayuda": "Up to 4 JPG, PNG, WEBP or PDF files, 5 MB max each.",
             "err_adjunto_cantidad": "You can attach up to 4 files.",
             "err_adjunto_tamano": "Each file can be 5 MB max (12 MB in total).",
             "err_adjunto_tipo": "We only accept JPG, PNG or WEBP photos and PDF documents.",
             "err_nombre": "Please enter your name.", "err_contacto": "Leave a valid email or a phone number so we can reply.",
             "err_consent": "We need your authorization to process your data before sending.",
             "err_paquete": "Please select a package.", "enviando": "Sending…",
             "err_limite": "We received several requests from your connection. Please wait a few minutes and try again, "
                           "or message us on WhatsApp."},
    "ident": {"titulo": "Your ID and your phone", "documento": "ID number", "celular": "Mobile phone",
              "continuar": "Continue", "primera": "Looks like it’s your first time.",
              "primera2": "Tell us your name so we can register you.", "nombres": "First names", "apellidos": "Last names",
              "correo": "Email (optional)",
              "acepta_correo": "I want to receive appointment confirmations, reminders and cancellation notices by email.",
              "registrar": "Register and continue", "cargando": "One moment…",
              "ph_celular": "3001234567", "ph_correo": "you@email.com",
              "err_datos": "Check your ID number and mobile phone (10 digits, starting with 3).",
              "err_consent": "To register we need your authorization to process your personal data.",
              "err_correo": "Enter a valid email, or untick the option to receive emails.",
              "consent": "I authorize {nombre} to process my personal data to manage my appointments and send me "
                         "messages about them.",
              "sin_auto": "We could not continue automatically. {termino} will contact you very soon to help you book.",
              "volver": "Back", "gracias": "Thank you",
              "familia": "Booking for your children or other relatives? Register yourself first, then add them from "
                         "My appointments."},
    "pie": {"horario": "Schedule", "direccion": "Address", "contacto": "Contact", "derechos": "All rights reserved.",
            "politica": "Data processing policy", "equipo": "Staff access", "inicio": "Go to home", "siguenos": "Follow us"},
    "asistente": {"titulo": "Appointment assistant", "aria": "Bliss, site assistant", "abrir": "Open or close Bliss",
                  "saludo": "Hi, I’m {nombre}. I can help you with appointments, hours and the clinic’s address.",
                  "opciones": [("agendar", "Book an appointment"), ("afuera", "I live abroad"),
                               ("direccion", "Address and hours"), ("otra", "Something else")],
                  "ya_paciente": "Already a patient? Use the same form.",
                  "afuera": "If you live outside Colombia, we start with a virtual assessment: tell us about your case and "
                            "you get specialized advice.",
                  "experiencia": "Pick your package and leave your details: we’ll write to you to plan your trip.",
                  "direccion": "We are at:", "mapa": "View on the map", "volver": "Back",
                  "otra": "Type your question and I’ll help.", "otra_sin": "Leave us a message and the clinic will reply.",
                  "aviso_ia": "I’m an AI assistant and I can make mistakes. Don’t type personal or health details: those go "
                              "only in the forms.",
                  "texto": "Your question", "enviar": "Send", "escribiendo": "Typing…",
                  "err_texto": "Write a message of up to {max} characters."},
    "barra": "Book appointment", "idioma_aria": "Switch language to Spanish",
}

COPIA = {"es": ES, "en": EN}
