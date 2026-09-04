import { useEffect, useMemo, useState } from 'react'
import { Button, Empty, Input, Select, Spin, Tag } from 'antd'
import { FileTextOutlined, SafetyCertificateOutlined, ShoppingCartOutlined } from '@ant-design/icons'
import { Link, useSearchParams } from 'react-router-dom'
import client from '../api/client'
import type { Product } from '../types/shop'

const priceBands = [
  { key: 'all', label: '全部商品' },
  { key: 'low', label: '300 元以下', max_price: 300 },
  { key: 'mid', label: '300.01 - 3000 元', min_price: 300.01, max_price: 3000 },
  { key: 'high', label: '3000.01 元以上', min_price: 3000.01 },
] as const

const categoryRules = [
  { label: '手机', keywords: ['手机', 'phone'] },
  { label: '耳机', keywords: ['耳机', 'buds', 'headphone'] },
  { label: '充电', keywords: ['充电', '电源', 'charger'] },
  { label: '数据线', keywords: ['数据线', '线'] },
  { label: '其他配件', keywords: ['路由', '保护', '壳', '膜', '支架'] },
]

const lowestPrice = (product: Product) => Math.min(...product.variants.filter((item) => item.available).map((item) => item.price))

export default function ShopHome() {
  const [searchParams] = useSearchParams()
  const [items, setItems] = useState<Product[]>([])
  const [brands, setBrands] = useState<string[]>([])
  const [keyword, setKeyword] = useState(() => searchParams.get('keyword') || '')
  const [brand, setBrand] = useState<string>()
  const [band, setBand] = useState<(typeof priceBands)[number]['key']>('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<'catalog' | 'network' | null>(null)
  const params = useMemo(() => {
    const activeBand = priceBands.find((item) => item.key === band)
    return { keyword: keyword || undefined, brand, min_price: activeBand && 'min_price' in activeBand ? activeBand.min_price : undefined, max_price: activeBand && 'max_price' in activeBand ? activeBand.max_price : undefined, page_size: 100 }
  }, [band, brand, keyword])
  const load = () => {
    setLoading(true)
    setError(null)
    client.get('/shop/products', { params }).then((response) => setItems(response.data.items)).catch((requestError) => {
      setItems([])
      setError(requestError.response?.status === 503 ? 'catalog' : 'network')
    }).finally(() => setLoading(false))
  }
  useEffect(() => { client.get('/shop/brands').then((response) => setBrands(response.data)).catch(() => undefined) }, [])
  useEffect(() => { load() }, [params])
  useEffect(() => { setKeyword(searchParams.get('keyword') || '') }, [searchParams])
  const categories = categoryRules.filter(({ keywords }) => items.some((product) => {
    const searchable = `${product.name} ${product.model || ''} ${product.description || ''}`.toLowerCase()
    return keywords.some((item) => searchable.includes(item))
  }))

  const featuredProduct = items.find((product) => product.image_url) || items[0]

  return <main className="shop-home page-wrap">
    <div className="shop-portal">
      <nav className="shop-category-menu" aria-label="全部商品分类">
        <h2>商品分类</h2>
        {categories.map((item) => <button key={item.label} type="button" onClick={() => setKeyword(item.keywords[0])}><b>{item.label}</b><span aria-hidden="true">官方目录</span></button>)}
        {!loading && categories.length === 0 && <span className="shop-category-menu__empty">目录加载后显示分类</span>}
      </nav>
      <section className="shop-hero" aria-label="商城主会场">
        <div className="shop-hero__content"><p className="shop-eyebrow">vivo · 小米官方目录</p><h1>发现值得入手的科技好物</h1><p>手机与实用配件，价格和可售规格均以品牌官方目录为准。</p><Link className="shop-hero__action" to={featuredProduct ? `/shop/products/${featuredProduct.id}` : '/shop'}>{featuredProduct ? '查看主推商品' : '浏览官方目录'}</Link></div>
        {featuredProduct?.image_url && <img className="shop-hero__image" src={featuredProduct.image_url} alt={`${featuredProduct.brand} ${featuredProduct.name}`} />}
      </section>
      <aside className="shop-service-panel" aria-label="用户服务">
        <div className="shop-service-panel__welcome"><span aria-hidden="true">M</span><div><b>欢迎来到品牌优选商城</b><small>官方目录每日更新</small></div></div>
        <div className="shop-service-panel__links"><Link to="/shop/orders"><FileTextOutlined />我的订单</Link><Link to="/shop/returns"><SafetyCertificateOutlined />退款售后</Link><Link to="/shop/cart"><ShoppingCartOutlined />购物车</Link></div>
        <div className="shop-service-panel__notice"><h2>商城快报</h2><p>商品价格和可售规格以实时目录为准。</p><p>订单与售后进度可在对应页面查询。</p></div>
      </aside>
    </div>
    <section className="shop-service-strip" aria-label="商城服务说明"><span><b>真实目录</b>vivo 与小米官方来源</span><span><b>价格透明</b>服务端实时价格</span><span><b>订单可查</b>下单后可查看订单状态</span><span><b>售后入口</b>可提交退款售后申请</span></section>
    <section className="shop-filters" aria-label="商品筛选">
      <Input aria-label="搜索商品" placeholder="搜索型号或商品名称" value={keyword} onChange={(event) => setKeyword(event.target.value)} onPressEnter={load} />
      <Select aria-label="按品牌筛选" allowClear placeholder="全部品牌" value={brand} onChange={setBrand} options={brands.map((item) => ({ label: item, value: item }))} />
      <Button type="primary" onClick={load}>搜索</Button>
    </section>
    <section aria-label="商品价格专区">
      <div className="shop-section-heading"><div><p className="shop-eyebrow">按预算探索</p><h2>价格专区</h2></div></div>
      <div className="shop-price-tabs" role="tablist" aria-label="按价格筛选">
        {priceBands.map((item) => <button key={item.key} className={band === item.key ? 'is-active' : ''} type="button" role="tab" aria-selected={band === item.key} onClick={() => setBand(item.key)}>{item.label}</button>)}
      </div>
    </section>
    {loading ? <div className="shop-loading" aria-live="polite"><Spin size="large" /><span>正在加载最新商品目录</span></div> : error === 'catalog' ? <Empty className="shop-empty" description="商品目录正在初始化，请稍后刷新"><Button type="primary" onClick={load}>重新检查</Button></Empty> : error ? <Empty className="shop-empty" description="商品加载失败，请检查网络后重试"><Button onClick={load}>重新加载</Button></Empty> : items.length === 0 ? <Empty className="shop-empty" description="没有找到符合条件的商品"><Button onClick={() => { setKeyword(''); setBrand(undefined); setBand('all') }}>清空筛选</Button></Empty> : <section className="shop-products shop-product-grid" aria-label="商品列表">{items.map((product) => <article className="product-card" key={product.id}>
      <Link className="product-card__image" to={`/shop/products/${product.id}`} aria-label={`查看 ${product.name} 详情`}><img src={product.image_url || '/placeholder-product.svg'} alt={`${product.brand} ${product.name}`} loading="lazy" /></Link>
      <div className="product-card__body"><Tag>{product.brand}</Tag><h3>{product.name}</h3><p>{product.model || product.description || '品牌官方精选商品'}</p><strong>¥{lowestPrice(product).toFixed(2)}</strong><span>起</span><Link to={`/shop/products/${product.id}`}>查看商品</Link></div>
    </article>)}</section>}
  </main>
}
