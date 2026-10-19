import numpy as np
from crypto_research.diagnostics import independent_indices, independent_link, calendar_covariance


def test_block_indices_are_seeded_and_calendar_bounded():
    one=independent_indices(37)
    two=independent_indices(37)
    assert one.shape==(4000,37)
    np.testing.assert_array_equal(one,two)
    assert one.min()>=0 and one.max()<37
    np.testing.assert_array_equal((np.diff(one[:,:28],axis=1)%37),np.ones((4000,27),dtype=int))


def test_coin_components_compound_on_new_net_nav():
    gross=np.array([[.1,.02],[-.03,.04],[.01,.08]])
    fees=np.full_like(gross,.001)
    linked_gross,linked_fees,linked_net,terminal=independent_link(gross,fees)
    daily=(gross-fees).sum(axis=1)
    nav=np.r_[1.,np.cumprod(1+daily)[:-1]]
    np.testing.assert_allclose(linked_gross,(gross*nav[:,None]).sum(axis=0))
    np.testing.assert_allclose(linked_fees,(fees*nav[:,None]).sum(axis=0))
    np.testing.assert_allclose(linked_net.sum(),terminal)
    np.testing.assert_allclose(terminal,np.prod(1+daily)-1)


def test_calendar_hac_keeps_actual_missing_day_lags():
    mask=np.array([True,False,True,True,True,True])
    x=np.column_stack([np.ones(mask.sum()),np.arange(mask.sum())])
    residual=np.array([.1,-.2,.15,-.05,.03])
    lag=1
    scores=np.zeros((len(mask),2));scores[mask]=x*residual[:,None]
    meat=scores.T@scores
    cross=scores[1:].T@scores[:-1]
    meat+=.5*(cross+cross.T)
    bread=np.linalg.inv(x.T@x)
    expected=(len(x)/(len(x)-x.shape[1]))*bread@meat@bread
    np.testing.assert_allclose(calendar_covariance(x,residual,mask,lag),expected)
    compressed=calendar_covariance(x,residual,np.ones(mask.sum(),dtype=bool),lag)
    assert not np.allclose(compressed,expected)
