// Fontes livres (OFL), empacotadas no build: nada vem da internet em tempo de uso.
import '@fontsource-variable/bodoni-moda'
import '@fontsource-variable/bodoni-moda/wght-italic.css'
import '@fontsource-variable/cinzel'
import '@fontsource-variable/inter'
import '@fontsource-variable/literata'
import '@fontsource-variable/literata/wght-italic.css'
import '@fontsource/ibm-plex-mono/400.css'
import './lib/fontes.css'      // fontes extras que o usuário pode escolher (geradas por gera_fontes.py)
import './app.css'
import { le, aplica } from './lib/aparencia.js'
import { mount } from 'svelte'
import App from './App.svelte'

aplica(le())      // antes de montar: a tela já nasce com o tema escolhido
export default mount(App, { target: document.getElementById('app') })
