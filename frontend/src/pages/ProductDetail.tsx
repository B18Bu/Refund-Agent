import { useEffect, useMemo, useState } from 'react'
import { Button, Empty, InputNumber, Select, Spin, message } from 'antd'
import { useNavigate, useParams } from 'react-router-dom'
import client from '../api/client'
import type { Product } from '../types/shop'

export default function ProductDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const [product, setProduct] = useState<Product>()
  const [variantId, setVariantId] = useState<number>()
  const [quantity, setQuantity] = useState(1)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    client.get(`/shop/products/${id}`).then((response) => {
      setProduct(response.data)
      setVariantId(response.data.variants.find((item: Product['variants'][number]) => item.available)?.id)
    }).catch(() => setFailed(true))
  }, [id])

  const selectedVariant = useMemo(() => product?.variants.find((item) => item.id === variantId), [product, variantId])
  const add = () => client.put(`/shop/cart/items/${variantId}`, { quantity }).then(() => message.success('已加入购物车')).catch(() => message.error('加入购物车失败，请先登录后重试'))

  if (failed) return <main className="page-wrap shop-subpage"><Empty description="商品暂时无法加载"><Button onClick={() => nav('/shop')}>返回商城</Button></Empty></main>
  if (!product) return <main className="page-wrap shop-loading" aria-live="polite"><Spin size="large" /><span>正在加载商品信息</span></main>

  return <main className="page-wrap product-detail">
    <button className="store-back" type="button" onClick={() => nav('/shop')}>← 返回商城</button>
    <section className="product-detail__layout" aria-labelledby="product-title">
      <div className="product-detail__image"><img src={product.image_url || '/placeholder-product.svg'} alt={`${product.brand} ${product.name}`} /></div>
      <div className="product-detail__info"><p className="shop-eyebrow">{product.brand} 官方目录</p><h1 id="product-title">{product.name}</h1><p className="product-detail__description">{product.model || product.description || '品牌官方目录同步商品，规格与价格以下方选择为准。'}</p>
        <section className="product-price" aria-label="商品价格"><span>官方目录价格</span><strong>¥{selectedVariant?.price.toFixed(2) || '--'}</strong></section>
        <label className="product-detail__label">选择规格<Select aria-label="选择规格" value={variantId} onChange={setVariantId} options={product.variants.filter((item) => item.available).map((item) => ({ value: item.id, label: item.variant_name }))} /></label>
        <label className="product-detail__label">购买数量<InputNumber aria-label="购买数量" min={1} value={quantity} onChange={(value) => setQuantity(value || 1)} /></label>
        <div className="product-detail__actions"><Button type="primary" size="large" disabled={!variantId} onClick={add}>加入购物车</Button><Button size="large" onClick={() => nav('/shop/cart')}>查看购物车</Button></div>
      </div>
    </section>
  </main>
}
