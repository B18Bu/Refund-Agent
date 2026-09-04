import { useEffect, useState } from 'react'
import { Button, Card, Empty, Input, Select, Space, Spin, Tag } from 'antd'
import { Link } from 'react-router-dom'
import client from '../api/client'
import type { Product } from '../types/shop'

export default function ShopHome() {
  const [items,setItems]=useState<Product[]>([]); const [brands,setBrands]=useState<string[]>([]); const [keyword,setKeyword]=useState(''); const [brand,setBrand]=useState<string>(); const [loading,setLoading]=useState(true); const [error,setError]=useState(false)
  const load=()=>{setLoading(true);setError(false);client.get('/shop/products',{params:{keyword:keyword||undefined,brand}}).then(r=>setItems(r.data.items)).catch(()=>setError(true)).finally(()=>setLoading(false))}
  useEffect(()=>{client.get('/shop/brands').then(r=>setBrands(r.data)).catch(()=>{});load()},[])
  return <div className="page-wrap"><Space direction="vertical" size="large" style={{width:'100%'}}><div><h1>精选商品</h1><Space wrap><Input placeholder="搜索商品" value={keyword} onChange={e=>setKeyword(e.target.value)} onPressEnter={load} style={{width:240}}/><Select allowClear placeholder="品牌" value={brand} onChange={setBrand} options={brands.map(x=>({label:x,value:x}))}/><Button type="primary" onClick={load}>搜索</Button><Link to="/shop/cart"><Button>购物车</Button></Link></Space></div>{loading?<Spin/>:error?<Empty description="加载失败"><Button onClick={load}>重试</Button></Empty>:items.length===0?<Empty description="暂无商品"/>:<div className="shop-grid">{items.map(p=><Card key={p.id} title={<Space>{p.brand}<Tag color="blue">{p.status}</Tag></Space>}><p>{p.name} {p.model}</p><p>{p.description||'官方精选商品'}</p><Link to={`/shop/products/${p.id}`}>查看详情</Link></Card>)}</div>}</Space></div>
}
