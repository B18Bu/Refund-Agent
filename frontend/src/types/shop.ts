export type ProductCategory = 'PHONE' | 'PERIPHERAL' | 'OTHER'
export type Product = { id:number; brand:string; name:string; model?:string; description?:string; image_url?:string; category?:ProductCategory; status:string; variants:{id:number; sku:string; variant_name:string; price:number; available:boolean}[] }
export type Order = { id:number; order_no:string; status:string; total_amount:number; currency:string; address_snapshot_json:Record<string,string>; items:{id:number; product_snapshot_json:Record<string,unknown>; quantity:number; unit_price:number; status:string}[] }
export type ReturnRequest = { id:number; return_no:string; order_id:number; order_item_id:number; status:string; reason:string; description?:string; ticket_id?:number }
export type CustomerAssistantReply = { answer:string; personalized:boolean; sources:{source_url:string; crawled_at:string|null}[] }
export type CustomerSupportConversation = { id:number; status:string }
export type CustomerSupportReply = { conversation_id:number; answer:string; intent:string; evidence:{products?:{product_id:number; source_url:string}[]; order_id?:number} }
export type CustomerPrivacyState = { enabled:boolean; preferences:{key:string; value:unknown; manual:boolean}[]; ignored_keys:string[] }
