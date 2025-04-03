import { useState, useContext } from 'react';
import { Button, Card, Form } from 'react-bootstrap';
import CreatableSelect from 'react-select/creatable';
import Input from './Atoms/Input';
import { isLigoUser } from '../../Utils/UserUtils';
import { UserContext } from '../../sessionUser';

const DetectorCard = ({ image, title, formik, channelOptions }) => {
    const [options, setOptions] = useState(channelOptions);
    const user = useContext(UserContext);

    const identifier = title.toLowerCase();
    const maximumFrequencyId = identifier + 'MaximumFrequency';
    const minimumFrequencyId = identifier + 'MinimumFrequency';
    const channelId = identifier + 'Channel';

    const isActive = formik.values[identifier];

    const toggleActive = () => {
        formik.setFieldValue(identifier, !isActive);
    };

    const channelSelectValue = isLigoUser(user)
        ? {
              value: formik.values[channelId],
              label: formik.values[channelId],
          }
        : {
              value: 'GWOSC',
              label: 'GWOSC',
          };

    const handleChange = (newValue, actionMeta) => {
        if (actionMeta.action === 'create-option') {
            setOptions([newValue, ...options]);
        }
        formik.setFieldValue(identifier + 'Channel', newValue.value);
    };

    return (
        <Card className={isActive ? 'gw-detector-card active' : 'gw-detector-card'}>
            <Card.Img variant="top" src={image} />
            <Card.Header className="h4">
                {title}
                <Button
                    data-testid={identifier + 'Active'}
                    className="float-right"
                    variant="outline-primary"
                    size="sm"
                    onClick={toggleActive}
                >
                    {isActive ? 'Deactivate' : 'Activate'}
                </Button>
            </Card.Header>
            <Card.Body>
                <Form.Group controlId={channelId}>
                    <Form.Label>Channel</Form.Label>
                    <CreatableSelect
                        className="gw-select"
                        classNamePrefix="gw-select"
                        isDisabled={!isActive || !isLigoUser(user)}
                        onChange={handleChange}
                        options={options}
                        value={channelSelectValue}
                    />
                    <Form.Text id={channelId + 'Help'}>Start typing for a custom channel.</Form.Text>
                </Form.Group>
                <Input
                    formik={formik}
                    title="Minimum frequency"
                    name={minimumFrequencyId}
                    type="number"
                    disabled={!isActive}
                />
                <Input
                    formik={formik}
                    title="Maximum frequency"
                    name={maximumFrequencyId}
                    type="number"
                    disabled={!isActive}
                />
            </Card.Body>
        </Card>
    );
};

export default DetectorCard;
