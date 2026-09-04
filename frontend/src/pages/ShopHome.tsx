import { useEffect, useMemo, useState } from 'react'
import { Button, Empty, Input, Select, Spin, Tag } from 'antd'
import { Link } from 'react-router-dom'
import client from '../api/client'
import type { Product } from '../types/shop'

const priceBands = [
  { key: 'all', label: '全部商品' },
  { key: 'low', label: '300 元以下', max_price: 300 },
  { key: 'mid', label: '300.01 - 3000 元', min_price: 300.01, max_price: 3000 },
  { key: 'high', label: '3000.01 元以上', min_price: 3000.01 },
] as const

const lowestPrice = (product: Product) => Math.min(...product.variants.filter((item) => item.available).map((item) => item.price))

export default function ShopHome() {
  const [items, setItems] = useState<Product[]>([])
  const [brands, setBrands] = useState<string[]>([])
  const [keyword, setKeyword] = useState('')
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

  return <main className="shop-home page-wrap">
    <section className="shop-hero" aria-labelledby="shop-title">
      <div><p className="shop-eyebrow">VIVO · OPPO 官方商品目录</p><h1 id="shop-title">好物，刚好适合你</h1><p>从实用配件到旗舰设备，所有价格均来自已保存的品牌商品目录。</p></div>
      <Link className="shop-hero__action" to="/shop/cart">查看购物车</Link>
    </section>
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
    {loading ? <div className="shop-loading" aria-live="polite"><Spin size="large" /><span>正在加载最新商品目录</span></div> : error === 'catalog' ? <Empty className="shop-empty" description="商品目录正在初始化，请稍后刷新"><Button type="primary" onClick={load}>重新检查</Button></Empty> : error ? <Empty className="shop-empty" description="商品加载失败，请检查网络后重试"><Button onClick={load}>重新加载</Button></Empty> : items.length === 0 ? <Empty className="shop-empty" description="没有找到符合条件的商品"><Button onClick={() => { setKeyword(''); setBrand(undefined); setBand('all') }}>清空筛选</Button></Empty> : <section className="shop-products" aria-label="商品列表">{items.map((product) => <article className="product-card" key={product.id}>
      <Link className="product-card__image" to={`/shop/products/${product.id}`} aria-label={`查看 ${product.name} 详情`}><img src={product.image_url || '/placeholder-product.svg'} alt={`${product.brand} ${product.name}`} loading="lazy" /></Link>
      <div className="product-card__body"><Tag>{product.brand}</Tag><h3>{product.name}</h3><p>{product.model || product.description || '品牌官方精选商品'}</p><strong>¥{lowestPrice(product).toFixed(2)}</strong><span>起</span><Link to={`/shop/products/${product.id}`}>查看商品</Link></div>
    </article>)}</section>}
  </main>
}
