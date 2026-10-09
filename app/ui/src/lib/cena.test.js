// node app/ui/src/lib/cena.test.js
import { pose, pilhas, eventos, falaDoAuditor } from './cena.js'

const eq = (a, b, o = '') => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${o}: ${JSON.stringify(a)} != ${JSON.stringify(b)}`) }
const soma = (p) => Object.values(p).reduce((s, x) => s + x, 0)

// a soma das pilhas é sempre o número de blocos propostos, em qualquer ponto do processamento
const passos = [
  { propostos: 10 }, { propostos: 10, conferidos: 6, com_problema: 2 }, { propostos: 10, conferidos: 10, com_problema: 4, corrigidos: 3 },
  { propostos: 10, conferidos: 10, com_problema: 4, corrigidos: 4, reconferidos: 4, em_disputa: 3 },
  { propostos: 10, conferidos: 10, com_problema: 4, corrigidos: 4, reconferidos: 4, em_disputa: 3, causa_tradutor: 1, causa_auditor: 1, causa_usuario: 1 }]
for (const c of passos) { eq(soma(pilhas(c)), 10, 'soma'); eq(soma(pilhas(c, false)), 10, 'soma sem juiz'); if (Object.values(pilhas(c)).some((x) => x < 0)) throw new Error('pilha negativa') }
eq(pilhas(passos[4]), { conferir: 0, corrigir: 0, disputa: 0, aprovados: 8, juiz: 1, voce: 1 }, 'fim')
eq(pilhas(passos[3], false).voce, 3, 'sem juiz, a disputa vai para você')

// poses
eq(pose({ papel: 'propondo', texto: '' }, 'propor', 'rodando').tradutor, 'folheia')
eq(pose({ papel: 'propondo', texto: 'abc' }, 'propor', 'rodando').tradutor, 'escreve')
eq(pose({ papel: 'propondo', texto: 'abc' }, 'propor', 'rodando', true).tradutor, 'espera')
eq(pose({ papel: 'conferindo', texto: '[' }, 'auditar', 'rodando'), { tradutor: 'olha-auditor', auditor: 'lupa', juiz: 'ausente', ato: 'conferindo' })
eq(pose({ papel: 'julgando', texto: '1:' }, 'julgar', 'rodando').juiz, 'julga')
eq(pose({ papel: 'julgando', texto: '1:' }, 'julgar', 'rodando').tradutor, 'olha-juiz')
eq(pose(null, 'propor', 'pausado').ato, 'pausado'); eq(pose(null, 'fim', 'concluido').juiz, 'ausente')

// eventos: uma mudança por consulta vira reação; salto ou duas de uma vez, não
eq(eventos({ propostos: 1 }, { propostos: 2 }), [{ tipo: 'proposto', de: 'tradutor', para: 'conferir' }])
eq(eventos({ conferidos: 1, com_problema: 0 }, { conferidos: 2, com_problema: 1 })[0].tipo, 'objecao')
eq(eventos({ conferidos: 1 }, { conferidos: 2 })[0].para, 'aprovados')
eq(eventos({ reconferidos: 0, em_disputa: 0 }, { reconferidos: 1, em_disputa: 1 })[0].tipo, 'disputa')
eq(eventos({ causa_auditor: 0 }, { causa_auditor: 1 })[0].para, 'juiz')
eq(eventos({ propostos: 1 }, { propostos: 5 }), [])
eq(eventos({ propostos: 1, conferidos: 0 }, { propostos: 2, conferidos: 1 }), [])
eq(eventos(null, { propostos: 2 }), [])

// fala do auditor: JSON pela metade
eq(falaDoAuditor('[{"trecho": "a \\"b\\"", "problema": "falta"}, {"trecho": "c", "probl'), [{ trecho: 'a "b"', problema: 'falta' }])
eq(falaDoAuditor('[]'), 'fiel'); eq(falaDoAuditor('[{"tre'), 'lendo'); eq(falaDoAuditor(''), 'lendo')
console.log('ok')
