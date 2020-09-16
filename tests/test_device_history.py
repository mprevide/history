import pytest
import falcon
from unittest.mock import MagicMock, Mock, patch
from history.api.models import DeviceHistory, HistoryUtil

class TestDeviceHistory:
    
    def test_parse_request1(self):
        request = MagicMock()
        request.params.keys.return_value = ['firstN', 'dateFrom', 'dateTo']
        req_content = {"firstN": 2, "dateFrom": "20190901", "dateTo": "20190910"}
        request.params.__getitem__.side_effect = lambda key: req_content[key]
        assert DeviceHistory.parse_request(request, 'test')

    def test_parse_request2(self):
        request = MagicMock()
        request.params.keys.return_value = ['lastN','dateFrom','dateTo']
        req_content = {"lastN":2,"dateFrom":"20190901" ,"dateTo":"20190910"}
        request.params.__getitem__.side_effect = lambda key: req_content[key]
        assert DeviceHistory.parse_request(request,'test')
    
    def test_parse_request_invalid_firstN(self):
        with pytest.raises(falcon.HTTPInvalidParam):
            request = MagicMock()
            request.params.keys.return_value = ['firstN', 'dateFrom', 'dateTo']
            req_content = {"firstN": "test"}
            request.params.__getitem__.side_effect = lambda key: req_content[key]
            DeviceHistory.parse_request(request, "test")

    def test_parse_request_invalid_lastN(self):
        with pytest.raises(falcon.HTTPInvalidParam):
            request = MagicMock()
            request.params.keys.return_value = ['lastN','dateFrom','dateTo']
            req_content = {"lastN":"test"}
            request.params.__getitem__.side_effect = lambda key: req_content[key]
            DeviceHistory.parse_request(request,"test")

    def test_parse_request_invalid_hLimit(self):
        with pytest.raises(falcon.HTTPInvalidParam):
            request = MagicMock()
            request.params.keys.return_value = ['hLimit','dateFrom','dateTo']
            req_content = {"hLimit":"test"}
            request.params.__getitem__.side_effect = lambda key: req_content[key]
            DeviceHistory.parse_request(request,"test")

    @patch('history.api.models.HistoryUtil.get_collection')
    @patch('history.api.models.DeviceHistory.get_single_attr')
    def test_on_get_single_attr(self,mock_historyu_get_collection, mock_get_single_attr):
        request = MagicMock()
        request.params.keys.return_value = ['attr']
        request.params.return_value = ['value']
        response = falcon.Response()
        mock_historyu_get_collection.return_value = { }
        with pytest.raises(falcon.HTTPNotFound):
            mock_get_single_attr.return_value = []
            DeviceHistory.on_get(request,response,'testid')
    
    @patch('history.api.models.HistoryUtil.get_collection')
    @patch('history.api.models.DeviceHistory.get_attrs')
    @patch('history.api.models.DeviceHistory.parse_request')
    def test_on_get_no_attr(self,mock_get_collection,mock_get_attrs,mock_parse_request):
        with patch('history.api.models.DeviceHistory.get_single_attr') as mock_get_attr:
            request = MagicMock()
            request.params.keys.return_value = []
            request.get_header.return_value = 'token'
            request.params.return_value = ['value']
            response = falcon.Response()
            
            attr_list = ['attr1','attr2']
            mock_get_attrs.__getitem__.side_effect = lambda key: attr_list[key]

            mock_parse_request.return_value = None
            mock_get_attr.return_value = ''
            
            DeviceHistory.on_get(request, response, 'test')

            assert response.status == falcon.HTTP_200    
