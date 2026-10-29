export function transportCosts(deliveryRequired, returnRequired, deliveryEstimate, returnEstimate) {
  const cents = (required, estimate) => {
    if (!required) return 0
    const fee = estimate?.fee
    return fee !== null && fee !== undefined && fee !== '' && Number.isFinite(Number(fee)) && Number(fee) >= 0
      ? Math.round(Number(fee) * 100) : null
  }
  const delivery = cents(deliveryRequired, deliveryEstimate)
  const collection = cents(returnRequired, returnEstimate)
  return {
    delivery: delivery === null ? null : delivery / 100,
    collection: collection === null ? null : collection / 100,
    total: delivery === null || collection === null ? null : (delivery + collection) / 100,
  }
}
