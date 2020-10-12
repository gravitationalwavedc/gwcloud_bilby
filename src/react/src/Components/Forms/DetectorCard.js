import React, { useState } from 'react';
import { Button, Card, Form } from 'react-bootstrap';
import CreatableSelect from 'react-select/creatable';

const activeDetectorStyle = {
    borderLeft: 'none', 
    borderRight: 'none', 
    borderBottom: 'none', 
    borderRadius: 0, 
    boxShadow: '0 4px 8px rgba(0, 0, 0, 0.2)'
};

const deactiveDetectorStyle = {
    borderLeft: 'none', 
    borderRight: 'none', 
    borderBottom: 'none', 
    borderRadius: 0
};

const DetectorCard = ({image, title, formik}) => {
    const [options, setOptions] = useState([
        {label: 'GWOCS', value: 'GWOCS'}, 
        {label: 'GDS-CALIB_STRAIN', value: 'GDS-CALIB_STRAIN'}, 
    ]);

    const identifier = title.toLowerCase();
    const maximumFrequencyId = identifier + 'MaximumFrequency';
    const minimumFrequencyId = identifier + 'MaximumFrequency';
    const channelId = identifier + 'Channel';

    const isActive = formik.values[identifier];

    const toggleActive = () => {
        formik.setFieldValue(identifier, !isActive);
    };
    
    const handleChange = (newValue, actionMeta) => {
        if(actionMeta.action === 'create-option'){
            setOptions([newValue, ...options]);
        }
        formik.setFieldValue(identifier + 'Channel', newValue.value);
    };

    return (
        <Card style={isActive ? activeDetectorStyle: deactiveDetectorStyle}>
            <Card.Img variant="top" src={image} style={{height: '60px', objectFit: 'cover', borderRadius: 0}}/>
            <Card.Header className="h4">
                {title}
                <Button 
                    className="float-right" 
                    variant="outline-primary" 
                    size="sm" 
                    onClick={toggleActive}>
                    {isActive ? 'Deactivate' : 'Activate' }
                </Button>
            </Card.Header>
            <Card.Body>
                <Form.Group controlId={channelId}>
                    <Form.Label>Channel</Form.Label>
                    <CreatableSelect 
                        onChange={handleChange}
                        options={options}
                        value={{value:formik.values[channelId], label: formik.values[channelId]}}
                    />
                </Form.Group>
                <Form.Group controlId={minimumFrequencyId}>
                    <Form.Label>Minimum Frequency</Form.Label>
                    <Form.Control 
                        name={minimumFrequencyId} 
                        {...formik.getFieldProps(minimumFrequencyId)}/>
                </Form.Group>
                <Form.Group controlId={maximumFrequencyId}>
                    <Form.Label>Maximum Frequency</Form.Label>
                    <Form.Control 
                        name={maximumFrequencyId} 
                        {...formik.getFieldProps(maximumFrequencyId)}/>
                </Form.Group>
            </Card.Body>
        </Card>
    );
};


export default DetectorCard;
