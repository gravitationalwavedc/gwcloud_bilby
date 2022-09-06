import React, {useEffect, useRef, useState} from 'react';
import {Button, CardDeck, Col, Row, Form} from 'react-bootstrap';
import Input from './Atoms/Input';
import RadioGroup from './Atoms/RadioGroup';
import DetectorCard from './DetectorCard';
import FormCard from './FormCard';
import hanfordImg from '../../assets/hanford.png';
import virgoImg from '../../assets/Virgo.jpg';
import livingstonImg from '../../assets/livingston.png';
import {hanford, virgo, livingston} from './channels';
import EventIDDropdown from '../Results/EventIDDropdown';
import {createFragmentContainer, graphql} from 'react-relay';
import initialValues from './initialValues';


const DataForm = ({formik, handlePageChange, data}) => {
    const [eventId, setEventId] = useState(initialValues.eventId);
    const isMounted = useRef();

    useEffect(() => {
        if (isMounted.current) {
            eventId ? formik.setFieldValue('triggerTime', eventId.gpsTime) : null;
            formik.setFieldValue('eventId', eventId);
        } else {
            isMounted.current = true;
        }
    }, [eventId]);

    return <React.Fragment>
        <Row>
            <Col>
                <FormCard title='Data'>
                    <Row>
                        <Col>
                            <RadioGroup
                                title='Types of data'
                                formik={formik}
                                name='dataChoice'
                                options={[
                                    {label: 'Real', value: 'real'},
                                    {label: 'Simulated', value: 'simulated'}
                                ]}/>
                        </Col>
                        <Col>
                            <EventIDDropdown
                                data={data}
                                modifiable={true}
                                eventId={eventId}
                                setEventId={setEventId}
                            />
                            <Input
                                formik={formik}
                                title='Trigger time (GPS)'
                                name='triggerTime'
                                type='number'
                                onChange={e => {
                                    setEventId(null);
                                    formik.getFieldProps('triggerTime').onChange(e);
                                }}
                            />
                        </Col>
                    </Row>
                    <Row>
                        <Col>
                            <Form.Group controlId='samplingFrequency'>
                                <Form.Label>Sampling frequency</Form.Label>
                                <Form.Control
                                    name='samplingFrequency'
                                    as='select'
                                    custom
                                    {...formik.getFieldProps('samplingFrequency')}>
                                    <option value='512'>512 hz</option>
                                    <option value='1024'>1024 hz</option>
                                    <option value='2048'>2048 hz</option>
                                    <option value='4096'>4096 hz</option>
                                    <option value='8192'>8192 hz</option>
                                    <option value='16384'>16384 hz</option>
                                </Form.Control>
                            </Form.Group>
                        </Col>
                        <Col>
                            <Form.Group controlId='signalDuration'>
                                <Form.Label>Signal duration</Form.Label>
                                <Form.Control
                                    name='signalDuration'
                                    as='select'
                                    custom
                                    {...formik.getFieldProps('signalDuration')}>
                                    <option value='4'>4 seconds</option>
                                    <option value='8'>8 seconds</option>
                                    <option value='16'>16 seconds</option>
                                    <option value='24'>24 seconds</option>
                                    <option value='32'>32 seconds</option>
                                    <option value='64'>64 seconds</option>
                                    <option value='128'>128 seconds</option>
                                </Form.Control>
                            </Form.Group>
                        </Col>
                    </Row>
                </FormCard>
            </Col>
        </Row>
        <CardDeck className='mb-3'>
            <DetectorCard channelOptions={hanford} title='Hanford' image={hanfordImg} formik={formik}/>
            <DetectorCard channelOptions={livingston} title='Livingston' image={livingstonImg} formik={formik}/>
            <DetectorCard channelOptions={virgo} title='Virgo' image={virgoImg} formik={formik}/>
        </CardDeck>
        <Row>
            <Col>
                <Button onClick={() => handlePageChange('signal')}>Save and continue</Button>
            </Col>
        </Row>
    </React.Fragment>;
};


export default createFragmentContainer(DataForm, {
    data: graphql`
        fragment DataForm_data on Query {
            ...EventIDDropdown_data
        }
    `
});

