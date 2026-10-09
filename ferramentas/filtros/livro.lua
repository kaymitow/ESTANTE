-- Filtro Pandoc do projeto: converte as marcas do Markdown dos livros em formatação
-- ([1.]{.pnum} = número de parágrafo; ::: assinatura / ::: fim = blocos alinhados).
local tex = FORMAT:match('latex') ~= nil

local function wrap(open, inlines, close)
  local out = { pandoc.RawInline('latex', open) }
  for _, i in ipairs(inlines) do out[#out + 1] = i end
  out[#out + 1] = pandoc.RawInline('latex', close)
  return out
end

function Span(el)
  if tex and el.classes:includes('pnum') then
    return wrap([[\textbf{]], el.content, '}')
  end
end

function Div(el)
  if not tex then return nil end
  if el.classes:includes('novapagina') then return pandoc.RawBlock('latex', [[\clearpage]]) end
  local abre, fecha
  if el.classes:includes('assinatura') then
    abre, fecha = [[\begin{flushright}\itshape]], [[\end{flushright}]]
  elseif el.classes:includes('anotacao') then
    abre, fecha = [[\begin{quote}\small\sffamily]], [[\end{quote}]]
  elseif el.classes:includes('fim') then
    abre, fecha = [[\begin{center}\bfseries]], [[\end{center}]]
  else
    return nil
  end
  local out = { pandoc.RawBlock('latex', abre) }
  for _, b in ipairs(el.content) do out[#out + 1] = b end
  out[#out + 1] = pandoc.RawBlock('latex', fecha)
  return out
end

-- no LaTeX a figura vetorial é o .pdf irmão do .svg (o EPUB usa o .svg)
function Image(el)
  if tex then el.src = el.src:gsub('%.svg$', '.pdf') end
  return el
end

-- <br> dentro do parágrafo = quebra de linha do original (verso, epígrafe); vale no PDF e no EPUB
function RawInline(el)
  if el.format == 'html' and el.text:match('^<br%s*/?>$') then return pandoc.LineBreak() end
end
